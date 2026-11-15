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


def test_browser_search_uses_current_home_not_import_time_home(tmp_path, monkeypatch):
    home = tmp_path / "home with spaces"
    profile = home / ".config/BraveSoftware/Brave-Browser/Default"
    profile.mkdir(parents=True)
    (profile / "Bookmarks").write_text("{}")
    monkeypatch.setenv("HOME", str(home))

    manager = UniversalProfileManager(object())
    found = manager.discover_profiles()
    assert [(p.browser_name, p.profile_name) for p in found] == [("Brave", "Default")]
    assert found[0].path == profile

