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
        assert first == {'type': 'state', 'active': False, 'reveal_on_demand': True, 'rules': {'whitelist': [], 'blacklist': []}, 'request_id': 'a'}
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
            daemon.deactivate()
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
        daemon.deactivate()
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


def test_corrupted_key_does_not_get_replaced(tmp_path):
    key = KeyManager(tmp_path)
    key.key_path.write_bytes(b'not-a-valid-encryption-key')
    with pytest.raises(ValueError, match='refusing to replace'):
        KeyManager(tmp_path)
    assert key.key_path.read_bytes() == b'not-a-valid-encryption-key'
