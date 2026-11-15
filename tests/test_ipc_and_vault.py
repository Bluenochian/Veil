"""IPC and vault safety tests."""
import json
import os
import socket
import sqlite3
import time
from pathlib import Path

import pytest

from veil.crypto import KeyManager, VaultCrypto
from veil.ipc_server import IPCServer, IPCClient
from veil.service import VeilService
from veil.vault import Vault


import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from veil import command
PROFILE = '11111111-1111-4111-8111-111111111111'
TOKEN = '11111111-1111-4111-8111-111111111112'


def request(client, payload):
    client.send(payload)
    result = client.receive(timeout=3)
    assert isinstance(result, dict), f"No IPC response to {payload['type']}"
    return result


def test_daemon_handshake_broadcast_and_socket_permissions(tmp_path, monkeypatch):
    monkeypatch.setattr(IPCServer, 'FALLBACK_SOCKET_DIR', tmp_path)
    path = tmp_path / 'veil.sock'
    daemon = VeilService(vault_dir=tmp_path / 'vault', socket_path=path, start_ipc=True)
    client = IPCClient(socket_path=path)
    try:
        assert client.connect()
        assert path.stat().st_mode & 0o777 == 0o600
        first = request(client, {'type': 'get_state', 'request_id': 'a'})
        assert first == {'type': 'state', 'active': False, 'reveal_on_demand': True,
                         'unlock_password_enabled': False,
                         'rules': {'whitelist': [], 'blacklist': []}, 'request_id': 'a'}
        reply = request(client, {'type': 'toggle', 'request_id': 'b'})
        assert reply['active'] is True
        assert reply['request_id'] == 'b'
        # Broadcast on the same socket can arrive before the command response.
        # A fresh client observes the authoritative state without relying on message ordering.
        other = IPCClient(socket_path=path)
        try:
            assert other.connect()
            state = request(other, {'type': 'get_state'})
            assert state['active'] is True
            daemon.unlock_guard.set_password('safe test password 123')
            daemon.deactivate(password='safe test password 123')
            # Receiving daemon state updates works for persistent clients.
            assert other.receive(timeout=3)['active'] is False
        finally:
            other.close()
    finally:
        client.close()
        daemon.stop()


def test_encrypted_tabs_and_profile_isolation(tmp_path):
    vault = Vault(tmp_path / 'vault.db', VaultCrypto(KeyManager(tmp_path)))
    profile1 = 'LiveBrowser:00000000-0000-4000-8000-000000000001'
    profile2 = 'LiveBrowser:00000000-0000-4000-8000-000000000002'
    token = '00000000-0000-4000-8000-000000000003'
    original = 'https://example.invalid/private?q=do-not-leak'
    vault.store_tab(profile1, token, original)
    assert vault.retrieve_tab(profile1, token) == original
    assert vault.retrieve_tab(profile2, token) is None
    assert original.encode() not in (tmp_path / 'vault.db').read_bytes()
    assert vault.clear_tab(profile2, token) is False
    assert vault.clear_tab(profile1, token) is True
    assert vault.retrieve_tab(profile1, token) is None
    assert (tmp_path / 'vault.db').stat().st_mode & 0o777 == 0o600


def test_bookmark_staging_idempotence_and_targeted_clear(tmp_path):
    vault = Vault(tmp_path / 'vault.db', VaultCrypto(KeyManager(tmp_path)))
    profile = 'LiveBrowser:00000000-0000-4000-8000-000000000001'
    url = 'https://example.invalid/one-private-bookmark'
    first = vault.store_live_bookmark(profile, 'browser-bm-1', 'parent-a', 4, url, 'Private', '123')
    second = vault.store_live_bookmark(profile, 'browser-bm-1', 'parent-a', 4, url, 'Private', '123')
    assert first == second
    rows = vault.retrieve_bookmarks(profile)
    assert len(rows) == 1
    assert rows[0]['parent_guid'] == 'parent-a'
    assert rows[0]['original_index'] == 4
    assert url.encode() not in (tmp_path / 'vault.db').read_bytes()
    assert vault.clear_bookmark_entry('LiveBrowser:another', first) is False
    assert vault.clear_bookmark_entry(profile, first) is True
    assert vault.retrieve_bookmarks(profile) == []


def test_native_commands_ack_and_lossless_history_guard(tmp_path, monkeypatch):
    monkeypatch.setattr(IPCServer, 'FALLBACK_SOCKET_DIR', tmp_path)
    daemon = VeilService(vault_dir=tmp_path / 'vault', start_ipc=False)
    profile_id = '00000000-0000-4000-8000-000000000001'
    token = '00000000-0000-4000-8000-000000000003'
    try:
        assert daemon._handle_ipc_message({'type': 'vault_tab', 'profile': profile_id, 'token': token, 'url': 'https://example.org'})['status'] == 'error'
        daemon.activate()
        stored = daemon._handle_ipc_message({'type': 'vault_tab', 'profile': profile_id, 'token': token, 'url': 'https://example.org'})
        assert stored['status'] == 'ok'
        bm = {'id': '123', 'url': 'https://www.pornhub.com/view_video.php?viewkey=5', 'title': 'video', 'parentId': '1', 'index': 3}
        assert daemon._handle_ipc_message({'type': 'vault_bookmark', 'profile': profile_id, 'item': bm})['status'] == 'ok'
        assert daemon._handle_ipc_message({'type': 'vault_history', 'item': {'url': bm['url']}})['status'] == 'unsupported'
        daemon.unlock_guard.set_password('safe test password 123')
        daemon.deactivate(password='safe test password 123')
        resolved = daemon._handle_ipc_message({'type': 'resolve_tab', 'profile': profile_id, 'token': token})
        assert resolved['url'] == 'https://example.org'
        assert daemon._handle_ipc_message({'type': 'resolve_tab', 'profile': '00000000-0000-4000-8000-000000000099', 'token': token})['status'] == 'error'
        bookmarks = daemon._handle_ipc_message({'type': 'list_live_bookmarks', 'profile': profile_id})['bookmarks']
        assert len(bookmarks) == 1
        assert bookmarks[0]['original_index'] == 3
        assert daemon._handle_ipc_message({'type': 'bookmark_restored', 'profile': profile_id, 'vault_id': bookmarks[0]['id']})['status'] == 'ok'
        assert daemon._handle_ipc_message({'type': 'clear_tab', 'profile': profile_id, 'token': token})['status'] == 'ok'
        assert daemon._handle_ipc_message({'type': 'list_live_bookmarks', 'profile': profile_id})['bookmarks'] == []
    finally:
        daemon.stop()


def test_socket_accepts_split_messages_and_skips_non_json(tmp_path, monkeypatch):
    monkeypatch.setattr(IPCServer, "FALLBACK_SOCKET_DIR", tmp_path)
    server = IPCServer(tmp_path / "connection.sock", on_message_callback=lambda msg, _: {"ok": msg["hello"]})
    server.start()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(2)
            client.connect(str(server.socket_path))
            client.sendall(b"not json\n" + b'{"hello":"wo')
            client.sendall(b'rld","request_id":"abc"}\n')
            packet = b""
            while b"\n" not in packet:
                packet += client.recv(1024)
            assert json.loads(packet.split(b"\n")[0]) == {"ok": "world", "request_id": "abc"}
    finally:
        server.stop()


def test_malformed_ipc_messages_keep_daemon_alive(tmp_path, monkeypatch):
    monkeypatch.setattr(IPCServer, 'FALLBACK_SOCKET_DIR', tmp_path)
    service = VeilService(vault_dir=tmp_path / 'vault', socket_path=tmp_path / 'veil.sock')
    client = IPCClient(socket_path=tmp_path / 'veil.sock')
    try:
        assert client.connect()
        for message in [[], {'type':'classify','url':'https://['},
                        {'type':'classify','url':42},
                        {'type':'vault_bookmark','profile':PROFILE,'item':{'id':'7','url':'https://pornhub.com','index':'nan'}},
                        {'type':'timer_set','minutes':'NaN'},
                        {'type':'timer_set','minutes':'inf'},
                        {'type':'timer_set','minutes':'wat'},
                        {'type':'timer_set','minutes':-1},
                        {'type':'vault_tab','profile':PROFILE,'token':TOKEN,'url':'https://['}]:
            client.send(message if isinstance(message, dict) else {'type':'classify', 'url':message})
            assert isinstance(client.receive(), dict)
        client.send({'type':'get_state'})
        assert client.receive()['type'] == 'state'
        assert not service.is_active
        assert service._timer is None
    finally:
        client.close()
        service.stop()


def test_duplicate_ipc_servers_cannot_claim_socket(tmp_path, monkeypatch):
    monkeypatch.setattr(IPCServer, 'FALLBACK_SOCKET_DIR', tmp_path)
    server1 = IPCServer(socket_path=tmp_path / 'sock', on_message_callback=lambda msg, _: {'yes': True})
    server2 = IPCServer(socket_path=tmp_path / 'sock')
    server1.start()
    try:
        with pytest.raises(RuntimeError, match='already listening'):
            server2.start()
        assert not server2.running
        client = IPCClient(socket_path=tmp_path / 'sock')
        try:
            assert client.connect()
            client.send({'type':'ping'})
            assert client.receive()['yes'] is True
        finally:
            client.close()
    finally:
        server2.stop()
        server1.stop()


def test_concurrent_bookmark_staging_exactly_once(tmp_path):
    vault = Vault(tmp_path / 'vault.db', VaultCrypto(KeyManager(tmp_path)))
    profile = 'LiveBrowser:' + PROFILE
    with ThreadPoolExecutor(max_workers=10) as pool:
        ids = list(pool.map(lambda _: vault.store_live_bookmark(profile, 'guid', 'root', 3, 'https://pornhub.com/private', 'secret'), range(60)))
    assert len(set(ids)) == 1
    assert len(vault.retrieve_bookmarks(profile)) == 1


def test_hundred_tab_batch_encryption_and_recovery(tmp_path):
    """Bulk responses must represent durable, profile-scoped ciphertext writes."""
    import uuid
    vault = Vault(tmp_path / 'batch' / 'vault.db', VaultCrypto(KeyManager(tmp_path / 'batch')))
    profile = 'LiveBrowser:' + PROFILE
    another = 'LiveBrowser:22222222-2222-4222-8222-222222222222'
    batch = [(str(uuid.uuid4()), f'https://pornhub.com/watch?id={i}') for i in range(100)]
    vault.store_tabs(profile, batch)
    assert vault.retrieve_tabs(profile, [token for token, _ in batch]) == dict(batch)
    assert vault.retrieve_tabs(another, [token for token, _ in batch]) == {}
    raw = (tmp_path / 'batch' / 'vault.db').read_bytes()
    assert b'https://pornhub.com' not in raw
    assert vault.clear_tabs(another, [token for token, _ in batch]) == 0
    assert vault.clear_tabs(profile, [token for token, _ in batch]) == 100
    assert vault.retrieve_tabs(profile, [token for token, _ in batch]) == {}


def test_hundred_tab_native_protocol_rejects_invalid_batches(tmp_path, monkeypatch):
    import uuid
    monkeypatch.setattr(IPCServer, 'FALLBACK_SOCKET_DIR', tmp_path)
    service = VeilService(vault_dir=tmp_path / 'vault', socket_path=tmp_path / 'veil.sock', start_ipc=False)
    service.is_active = True
    tokens = [str(uuid.uuid4()) for _ in range(100)]
    batch = [{'token': token, 'url': f'https://pornhub.com/a/{i}'} for i, token in enumerate(tokens)]
    try:
        invalid = [*batch[:-1], {'token': tokens[-1], 'url': 'https://['}]
        reply = service._handle_ipc_message({'type':'vault_tabs','profile':PROFILE,'tabs':invalid})
        assert reply['status'] == 'error'
        assert not service.vault.retrieve_tabs('LiveBrowser:'+PROFILE, tokens)
        for items in ([*batch, batch[0]], [*batch, {'token': tokens[0], 'url':'https://example.com'}],
                      [{'token': tokens[0], 'url':'file:///etc/passwd'}], []):
            assert service._handle_ipc_message({'type':'vault_tabs','profile':PROFILE,'tabs':items})['status'] == 'error'
        reply = service._handle_ipc_message({'type':'vault_tabs','profile':PROFILE,'tabs':batch})
        assert reply['status'] == 'ok' and reply['tokens'] == tokens
        # No original URL can be resolved while protection is active.
        assert service._handle_ipc_message({'type':'resolve_tabs','profile':PROFILE,'tokens':tokens})['status'] == 'error'
        service.is_active = False
        answer = service._handle_ipc_message({'type':'resolve_tabs','profile':PROFILE,'tokens':tokens})
        assert answer['status'] == 'ok'
        assert len(answer['tabs']) == 100
        assert answer['tabs'][tokens[10]] == 'https://pornhub.com/a/10'
        assert service._handle_ipc_message({'type':'resolve_tabs','profile':PROFILE,'tokens':[tokens[0],tokens[0]]})['status'] == 'error'
        assert service._handle_ipc_message({'type':'clear_tabs','profile':PROFILE,'tokens':tokens})['status'] == 'ok'
        assert service.vault.retrieve_tabs('LiveBrowser:'+PROFILE, tokens) == {}
    finally:
        service.stop()

