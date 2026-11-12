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
        service.deactivate()
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


def test_key_file_symlink_is_rejected(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    key_source = tmp_path / "outside.key"
    key_source.write_bytes(os.urandom(32))
    (root / "veil.key").symlink_to(key_source)
    with pytest.raises(ValueError, match="symlink"):
        KeyManager(root)


def test_extension_pages_not_public_and_unused_autoplay_script_removed():
    root = Path(__file__).resolve().parent.parent
    for family in ("chrome", "firefox"):
        base = root / "browser-extension" / family
        manifest = json.loads((base / "manifest.json").read_text())
        assert "web_accessible_resources" not in manifest
        assert not (base / "content.js").exists()
        assert (base / "paused.html").exists()
        assert (base / "paused.js").exists()
