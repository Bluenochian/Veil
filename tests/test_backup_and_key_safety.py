"""Backup compatibility and fail-closed recovery checks."""
import base64
import json
import os
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

from veil.crypto import KeyManager, VaultCrypto, VaultDecryptionError, decrypt_with_passphrase
from veil.service import VeilService
from veil.vault import Vault


import sqlite3


PROFILE = "LiveBrowser:11111111-1111-4111-8111-111111111111"
TOKEN = "11111111-1111-4111-8111-111111111112"
PASSPHRASE = "a long unique test passphrase"


def make_vault(path):
    return Vault(path / "vault.db", VaultCrypto(KeyManager(path)))


def test_new_backups_require_long_passphrases_and_round_trip(tmp_path):
    vault = make_vault(tmp_path / "live")
    vault.store_tab(PROFILE, TOKEN, "https://example.invalid/private")
    output = tmp_path / "secure.veilvault"
    for weak in ("a", "short", "123456789012345"):
        with pytest.raises(ValueError, match="at least 16"):
            vault.export_vault(output, weak)
        assert not output.exists()

    vault.export_vault(output, PASSPHRASE)
    encrypted = output.read_bytes()
    assert encrypted.startswith(Vault.BACKUP_MAGIC)
    assert b"example.invalid" not in encrypted
    assert encrypted != vault.db_path.read_bytes()
    with pytest.raises(ValueError, match="decryption failed"):
        make_vault(tmp_path / "wrong-password").import_vault(output, "not the correct passphrase")

    restored = make_vault(tmp_path / "restore")
    restored.import_vault(output, PASSPHRASE)
    assert restored.retrieve_tab(PROFILE, TOKEN) == "https://example.invalid/private"


def test_old_pbkdf2_archives_remain_importable(tmp_path):
    vault = make_vault(tmp_path / "source")
    original = "https://example.invalid/older-backup"
    vault.store_tab(PROFILE, TOKEN, original)
    modern = tmp_path / "modern.veilvault"
    vault.export_vault(modern, PASSPHRASE)
    encoded = modern.read_bytes()[len(Vault.BACKUP_MAGIC):].strip().decode("ascii")
    plaintext = decrypt_with_passphrase(encoded, PASSPHRASE)

    # Rebuild exactly the old v1 salt+nonce+AES-GCM envelope, including its
    # original 100k PBKDF2 work factor and a short historical password.
    old_password = "old"
    salt, nonce = os.urandom(16), os.urandom(12)
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100_000)
    secret = kdf.derive(old_password.encode("utf-8"))
    ciphertext = AESGCM(secret).encrypt(nonce, plaintext.encode("utf-8"), None)
    old_archive = tmp_path / "legacy.veilvault"
    old_archive.write_bytes(
        Vault.LEGACY_BACKUP_MAGIC +
        base64.urlsafe_b64encode(salt + nonce + ciphertext) + b"\n"
    )

    other = make_vault(tmp_path / "old-restore")
    other.import_vault(old_archive, old_password)
    assert other.retrieve_tab(PROFILE, TOKEN) == original


def test_vault_decryption_error_keeps_record_and_reports_failure(tmp_path):
    service = VeilService(
        vault_dir=tmp_path / "service", socket_path=tmp_path / "service.sock", start_ipc=False
    )
    profile_id = PROFILE.removeprefix("LiveBrowser:")
    try:
        service.activate()
        answer = service._handle_ipc_message({
            "type": "vault_tab", "profile": profile_id, "token": TOKEN,
            "url": "https://example.invalid/private",
        })
        assert answer["status"] == "ok"
        service.unlock_guard.set_password('safe test password 123')
        service.deactivate(password='safe test password 123')
        with service.vault._get_connection() as conn:
            conn.execute("UPDATE vault_tabs SET url_enc = ? WHERE token = ?", ("invalid-tag", TOKEN))
        with pytest.raises(VaultDecryptionError, match="could not be decrypted"):
            service.vault.retrieve_tab(PROFILE, TOKEN)

        response = service._handle_ipc_message({
            "type": "resolve_tab", "profile": profile_id, "token": TOKEN
        })
        assert response["type"] == "tab_resolve"
        assert response["status"] == "error"
        assert "could not be decrypted" in response["error"]
        assert service.vault.count_concealed_items()["tabs"] == 1
    finally:
        service.stop()


def test_backup_error_does_not_corrupt_existing_database(tmp_path):
    source = Vault(tmp_path / 'old' / 'vault.db', VaultCrypto(KeyManager(tmp_path / 'old')))
    profile = PROFILE
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


def test_portable_backup_roundtrip_all_tables_and_key_isolation(tmp_path):
    old = make_vault(tmp_path / "original")
    link = "https://private.example.com/view?q=nonpublic"
    token = "00000000-0000-4000-8000-000000000003"
    old.store_tab("LiveBrowser:11111111-1111-4111-8111-111111111111", token, link)
    old.store_live_bookmark("BrowserA", "bookmark-1", "toolbar", 2, link, "My bookmark")
    old.store_history_batch("BrowserA", [(18, link, "Secret", 2, 0, 111, 0, "adult")], [(29, 18, 111, 0, 1, 0, 8)])
    old.store_top_sites("BrowserA", [(link, 7, "Top secret")])
    old.store_firefox_places("FirefoxA", [(12, link, "Secret place", 1, 0, 100, 123, "g", "adult")],
                             [(15, 1, 12, 3, 0, "Secret bookmark", 111, 222, "g2")],
                             [(16, 0, 12, 99, 1, 0)])
    secret = "long portable test passphrase"
    output = tmp_path / "portable.veilvault"
    exported = old.export_vault(output, secret)
    assert output.stat().st_mode & 0o777 == 0o600
    assert output.read_bytes().startswith(Vault.BACKUP_MAGIC)
    assert link.encode() not in output.read_bytes()
    assert exported == {name: 1 for name in Vault.BACKUP_FIELDS}

    new = make_vault(tmp_path / "new-computer")
    assert new.crypto.km.key != old.crypto.km.key
    with pytest.raises(ValueError, match="decryption failed"):
        new.import_vault(output, "wrong passphrase")
    assert new.count_concealed_items()["tabs"] == 0
    imported = new.import_vault(output, secret)
    assert imported == exported
    assert new.retrieve_tab("LiveBrowser:11111111-1111-4111-8111-111111111111", token) == link
    assert new.retrieve_bookmarks("BrowserA")[0]["url"] == link
    assert new.retrieve_history("BrowserA")["urls"][0]["url"] == link
    assert new.retrieve_top_sites("BrowserA")[0]["url"] == link
    assert new.retrieve_firefox_places("FirefoxA")["places"][0]["url"] == link
    assert new.count_concealed_items()["tabs"] == 1
    assert new.count_concealed_items()["history_visits"] == 2

    # A repeated import must be wholly rolled back, not partially reinserted.
    with pytest.raises(sqlite3.IntegrityError):
        new.import_vault(output, secret)
    assert new.count_concealed_items()["bookmarks"] == 2
    assert new.retrieve_bookmarks("BrowserA")[0]["url"] == link
    with pytest.raises(FileExistsError):
        old.export_vault(output, secret)


def test_corrupt_encrypted_source_is_not_backed_up_as_empty(tmp_path):
    vault = make_vault(tmp_path / "vault")
    vault.store_tab("LiveBrowser:A", "token", "https://secret.example")
    with vault._get_connection() as conn:
        conn.execute("UPDATE vault_tabs SET url_enc=?", ("not-valid-ciphertext",))
    target = tmp_path / "bad.veilvault"
    with pytest.raises(Exception):
        vault.export_vault(target, "abc")
    assert not target.exists()

