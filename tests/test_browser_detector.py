from pathlib import Path
from veil.browsers.detector import UniversalProfileManager
from veil.vault import Vault
from veil.crypto import VaultCrypto, KeyManager


def test_profile_discovery(tmp_path):
    vault = Vault(tmp_path / "vault.db", VaultCrypto(KeyManager(tmp_path)))
    upm = UniversalProfileManager(vault)
    # Managers should initialize cleanly without exceptions
    assert isinstance(upm.managers, list)


def test_shred_all_caches(tmp_path):
    vault = Vault(tmp_path / "vault.db", VaultCrypto(KeyManager(tmp_path)))
    upm = UniversalProfileManager(vault)
    results = upm.shred_all_caches()
    assert isinstance(results, dict)
