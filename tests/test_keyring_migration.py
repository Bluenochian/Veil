"""First-run and migration safety for the desktop keyring."""
import os
import socket
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor

import pytest

from veil.crypto import KeyManager, KeyringUnavailable, VaultCrypto
from veil.vault import Vault


def test_new_vault_only_stores_key_in_secret_service(tmp_path):
    root = tmp_path / "new"
    key = KeyManager(root)
    assert len(key.key) == 32
    assert not key.key_path.exists()
    assert key.marker_path.exists()
    assert key.marker_path.stat().st_mode & 0o777 == 0o600
    assert key.lock_path.stat().st_mode & 0o777 == 0o600
    assert KeyManager(root).key == key.key


def test_migrates_legacy_key_without_changing_encrypted_vault(tmp_path):
    root = tmp_path / "old"
    root.mkdir()
    legacy = os.urandom(32)
    (root / "veil.key").write_bytes(legacy)
    # Simulate an existing installation: the database is already encrypted
    # with the key from the plaintext file BEFORE the migration runs.
    old_vault = Vault(root / "vault.db", VaultCrypto(SimpleNamespace(key=legacy)))
    old_vault.store_tab("LiveBrowser:A", "a-token", "https://example.invalid/private")
    ciphertext = (root / "vault.db").read_bytes()
    manager = KeyManager(root)
    assert manager.key == legacy
    assert not manager.key_path.exists()
    assert (root / "vault.db").read_bytes() == ciphertext
    assert Vault(root / "vault.db", VaultCrypto(KeyManager(root))).retrieve_tab(
        "LiveBrowser:A", "a-token"
    ) == "https://example.invalid/private"


def test_migration_failure_preserves_old_key(tmp_path, monkeypatch):
    root = tmp_path / "old"
    root.mkdir()
    legacy = os.urandom(32)
    (root / "veil.key").write_bytes(legacy)

    class FailingStore:
        def __init__(self, _dir): pass
        def lookup(self): return None
        def store(self, _key): raise KeyringUnavailable("locked")

    monkeypatch.setattr(KeyManager, "STORE_CLASS", FailingStore)
    with pytest.raises(KeyringUnavailable, match="locked"):
        KeyManager(root)
    assert (root / "veil.key").read_bytes() == legacy


def test_missing_wallet_never_creates_plaintext_fallback(tmp_path, monkeypatch):
    class UnavailableStore:
        def __init__(self, _dir): pass
        def lookup(self): raise KeyringUnavailable("unavailable")
        def store(self, _key): raise AssertionError("should not store")

    monkeypatch.setattr(KeyManager, "STORE_CLASS", UnavailableStore)
    with pytest.raises(KeyringUnavailable, match="unavailable"):
        KeyManager(tmp_path / "new")
    assert not (tmp_path / "new" / "veil.key").exists()


def test_existing_database_without_key_does_not_get_new_key(tmp_path):
    root = tmp_path / "lost"
    root.mkdir()
    (root / "vault.db").write_bytes(b"old-encrypted-database")
    with pytest.raises(KeyringUnavailable, match="Refusing to create a new key"):
        KeyManager(root)


def test_marker_without_key_does_not_get_new_key(tmp_path):
    root = tmp_path / "lost"
    root.mkdir()
    (root / ".keyring-initialized").write_text("initialized\n")
    with pytest.raises(KeyringUnavailable, match="Refusing to create a new key"):
        KeyManager(root)


def test_mismatch_between_legacy_file_and_keyring_fails(tmp_path, isolated_secret_service):
    root = tmp_path / "both"
    original = KeyManager(root).key
    legacy = os.urandom(32)
    (root / "veil.key").write_bytes(legacy)
    with pytest.raises(KeyringUnavailable, match="disagree"):
        KeyManager(root)
    assert (root / "veil.key").read_bytes() == legacy
    assert isolated_secret_service[str(root.resolve())] == original


def test_simultaneous_new_processes_get_same_key(tmp_path):
    root = tmp_path / "concurrent"
    with ThreadPoolExecutor(max_workers=8) as workers:
        keys = list(workers.map(lambda _: KeyManager(root).key, range(12)))
    assert len(set(keys)) == 1
    assert not (root / "veil.key").exists()


def test_active_daemon_blocks_legacy_migration(tmp_path):
    root = tmp_path / "running"
    root.mkdir()
    legacy = os.urandom(32)
    (root / "veil.key").write_bytes(legacy)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind(str(root / "veil.sock"))
        listener.listen(1)
        with pytest.raises(KeyringUnavailable, match="Stop the running Veil"):
            KeyManager(root)
    assert (root / "veil.key").read_bytes() == legacy


def test_invalid_legacy_key_never_replaced(tmp_path):
    root = tmp_path / "corrupt"
    root.mkdir()
    (root / "veil.key").write_bytes(b"bad")
    with pytest.raises(ValueError, match="refusing to replace"):
        KeyManager(root)


def test_migration_keeps_file_when_wallet_readback_is_wrong(tmp_path, monkeypatch):
    root = tmp_path / "interrupted"
    root.mkdir()
    legacy = os.urandom(32)
    (root / "veil.key").write_bytes(legacy)

    class CorruptReadback:
        def __init__(self, _dir): pass
        def lookup(self): return None if not hasattr(self, "saved") else os.urandom(32)
        def store(self, key): self.saved = key

    monkeypatch.setattr(KeyManager, "STORE_CLASS", CorruptReadback)
    with pytest.raises(KeyringUnavailable, match="verification failed"):
        KeyManager(root)
    assert (root / "veil.key").read_bytes() == legacy


def test_wallet_adapter_keeps_secret_out_of_process_arguments(tmp_path, monkeypatch):
    import base64
    import subprocess
    import veil.crypto as mod

    secret = os.urandom(32)
    encoded = base64.urlsafe_b64encode(secret)
    calls = []

    def fake_run(argv, *, input, stdout, stderr, timeout, check):
        calls.append((argv, input))
        if argv[1] == "store":
            return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")
        return subprocess.CompletedProcess(argv, 0, stdout=encoded, stderr=b"")

    monkeypatch.setattr(mod.shutil, "which", lambda command: "/usr/bin/secret-tool")
    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    adapter = mod.SecretToolStore(tmp_path)
    adapter.store(secret)
    assert adapter.lookup() == secret
    assert calls[0][1] == encoded
    assert secret not in repr(calls).encode()
    assert encoded not in repr([call[0] for call in calls]).encode()
    assert calls[0][0][0:3] == [
        "secret-tool", "store", "--label=Veil encrypted vault key",
    ]


def test_wallet_adapter_missing_backend_is_fail_closed(tmp_path, monkeypatch):
    import veil.crypto as mod

    monkeypatch.setattr(mod.shutil, "which", lambda command: None)
    with pytest.raises(KeyringUnavailable, match="requires secret-tool"):
        mod.SecretToolStore(tmp_path).lookup()
