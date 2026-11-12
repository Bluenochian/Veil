"""Linux integration and recovery tests."""
import json
import math
import os
import random
import socket
import string
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from veil import __version__, command
from veil.classifier import UniversalClassifier
from veil.crypto import KeyManager, VaultCrypto
from veil.ipc_server import IPCClient, IPCServer
from veil.service import VeilService
from veil.vault import Vault

PROFILE = '11111111-1111-4111-8111-111111111111'
TOKEN = '11111111-1111-4111-8111-111111111112'

def test_invalid_urls_do_not_crash_classifier(tmp_path):
    classifier = UniversalClassifier(rules_path=tmp_path / 'rules.json')
    assert not classifier.classify_url('https://[').is_sensitive
    assert not classifier.classify_url(123).is_sensitive
    assert classifier.classify_url('https://pornhub.com/').is_sensitive
    assert not classifier.classify_url('https://github.com/repo').is_sensitive
    # Fuzz malformed authority, Unicode, fragment and encoding combinations.
    rng = random.Random(70513)
    alphabet = string.ascii_letters + string.digits + '%:#@[]\\/?\x00' + '🌙'
    for _ in range(1500):
        value = ''.join(rng.choice(alphabet) for _ in range(rng.randint(0, 90)))
        result = classifier.classify_url('https://' + value)
        assert isinstance(result.is_sensitive, bool)


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


def test_native_registration_detects_system_entrypoint(tmp_path, monkeypatch):
    fake = tmp_path / 'system' / 'veil-native-host'
    fake.parent.mkdir()
    fake.write_text('#!/bin/sh\nexit 0\n')
    fake.chmod(0o755)
    called=[]
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setattr(command, 'package_root', str(tmp_path / 'missing-package'))
    monkeypatch.setattr('shutil.which', lambda cmd: str(fake) if cmd == 'veil-native-host' else None)
    monkeypatch.setattr('veil.native_host.installer.install_manifests', lambda path: called.append(path) or [tmp_path / 'manifest.json'])
    assert command.cmd_install_extension(SimpleNamespace()) is None
    assert called == [fake]


def test_native_registration_fails_without_host(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setattr(command, 'package_root', str(tmp_path / 'missing-package'))
    monkeypatch.setattr('shutil.which', lambda cmd: None)
    assert command.cmd_install_extension(SimpleNamespace()) == 1


def test_backup_error_does_not_corrupt_existing_database(tmp_path):
    source = Vault(tmp_path / 'old' / 'vault.db', VaultCrypto(KeyManager(tmp_path / 'old')))
    profile = 'LiveBrowser:' + PROFILE
    source.store_tab(profile, TOKEN, 'https://private.example.com/sensitive')
    backup = tmp_path / 'vault.veilvault'
    source.export_vault(backup, 'a strong local passphrase')
    target = Vault(tmp_path / 'new' / 'vault.db', VaultCrypto(KeyManager(tmp_path / 'new')))
    original = target.store_live_bookmark(profile, 'keep', 'root', 0, 'https://example.net', 'keep')
    with pytest.raises(ValueError):
        target.import_vault(backup, 'wrong passphrase')
    assert target.retrieve_bookmarks(profile)[0]['id'] == original
    assert target.retrieve_tab(profile, TOKEN) is None
    target.import_vault(backup, 'a strong local passphrase')
    assert target.retrieve_tab(profile, TOKEN) == 'https://private.example.com/sensitive'


def test_release_manifest_and_resources_consistent():
    root = Path(__file__).resolve().parents[1]
    manifests = [json.loads((root/'browser-extension'/browser/'manifest.json').read_text()) for browser in ('chrome','firefox')]
    assert manifests[0]['version'] == manifests[1]['version'] == __version__
    for browser, manifest in zip(('chrome','firefox'), manifests):
        assert (root/'browser-extension'/browser/'background.js').exists()
        assert (root/'browser-extension'/browser/'paused.html').exists()
        assert 'nativeMessaging' in manifest['permissions']
        for size in (16,48,128):
            assert (root/'browser-extension'/browser/'icons'/f'icon{size}.png').exists()


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
