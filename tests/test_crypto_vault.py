import os
import pytest
from veil.crypto import KeyManager, VaultCrypto
from veil.vault import Vault


@pytest.fixture
def temp_vault(tmp_path):
    km = KeyManager(tmp_path)
    crypto = VaultCrypto(km)
    db_file = tmp_path / "test_vault.db"
    return Vault(db_file, crypto)


def test_encryption_roundtrip(tmp_path):
    km = KeyManager(tmp_path)
    crypto = VaultCrypto(km)
    payload = b"sensitive_history_payload_12345"
    encrypted = crypto.encrypt(payload)
    assert encrypted != payload
    decrypted = crypto.decrypt(encrypted)
    assert decrypted == payload


def test_vault_bookmark_storage(temp_vault):
    temp_vault.store_bookmark(
        profile="Profile 1",
        guid="guid-101",
        parent_guid="toolbar",
        parent_name="Bookmarks Bar",
        original_index=0,
        url="https://stake.com/casino",
        title="Stake Casino",
        date_added="13300000000",
        meta={"category": "GAMBLING_WAGERING"}
    )
    assert temp_vault.count_concealed_items()["bookmarks"] == 1
    bm = temp_vault.retrieve_bookmarks("Profile 1")
    assert len(bm) == 1
    assert bm[0]["url"] == "https://stake.com/casino"
    assert bm[0]["meta"]["category"] == "GAMBLING_WAGERING"


def test_vault_state_persistence(temp_vault):
    assert temp_vault.get_state("is_active", False) is False
    temp_vault.set_state("is_active", True)
    assert temp_vault.get_state("is_active", False) is True
