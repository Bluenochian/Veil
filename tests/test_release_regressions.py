"""Vault portability, service status, and transition tests."""
import json
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from veil import command
from veil.crypto import KeyManager, VaultCrypto
from veil.ipc_server import IPCServer
from veil.service import VeilService
from veil.vault import Vault


def make_vault(root):
    return Vault(root / "vault.db", VaultCrypto(KeyManager(root)))


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


def test_offline_toggle_and_status_cannot_claim_protection(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(command, "get_ipc_client", lambda: None)
    vault = make_vault(tmp_path / ".config" / "veil")
    vault.set_state("is_active", True)
    assert command.cmd_toggle(SimpleNamespace()) == 1
    assert command.cmd_boss_key(SimpleNamespace()) == 1
    assert command.cmd_panic(SimpleNamespace()) == 1
    assert "not running" in capsys.readouterr().err
    assert vault.get_state("is_active") is True  # wasn't changed by offline CLI
    assert command.cmd_status(SimpleNamespace(json=True)) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["active"] is False
    assert status["saved_active"] is True
    assert status["daemon_running"] is False
    command.cmd_stats(SimpleNamespace())
    assert "STANDBY" in capsys.readouterr().out


def test_daemon_rule_sync_and_whitelist_priority(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    server = VeilService(vault_dir=tmp_path / "vault", socket_path=tmp_path / "sock", start_ipc=False)
    broadcasts = []
    server.ipc.broadcast = broadcasts.append
    try:
        initial = server._handle_ipc_message({"type": "get_state"})
        assert initial["rules"] == {"whitelist": [], "blacklist": []}
        server._handle_ipc_message({"type": "rules_add", "rule_type": "black", "domain": "*.example.org"})
        assert broadcasts[-1]["rules"]["blacklist"] == ["*.example.org"]
        assert server.classifier.classify_url("https://abc.example.org/blog").is_sensitive
        server._handle_ipc_message({"type": "rules_add", "rule_type": "white", "domain": "abc.example.org"})
        assert not server.classifier.classify_url("https://abc.example.org/blog").is_sensitive
        server._handle_ipc_message({"type": "rules_remove", "rule_type": "white", "domain": "abc.example.org"})
        assert server.classifier.classify_url("https://abc.example.org/blog").is_sensitive
        assert broadcasts[-1]["rules"]["whitelist"] == []
    finally:
        server.stop()


def test_rapid_on_off_transitions_are_serialized(tmp_path, monkeypatch):
    monkeypatch.setattr(IPCServer, "FALLBACK_SOCKET_DIR", tmp_path)
    service = VeilService(vault_dir=tmp_path / "vault", socket_path=tmp_path / "sock", start_ipc=False)
    restore_started, finish_restore = threading.Event(), threading.Event()
    overlaps = []
    states = []
    def restore():
        restore_started.set()
        assert finish_restore.wait(timeout=4)
    def conceal(classifier):
        if restore_started.is_set() and not finish_restore.is_set():
            overlaps.append(True)
    service.profile_manager.conceal_all = conceal
    service.profile_manager.restore_all = restore
    service.ipc.broadcast = lambda state: states.append(state["active"])
    try:
        service.activate()
        with ThreadPoolExecutor(max_workers=2) as pool:
            off = pool.submit(service.deactivate)
            assert restore_started.wait(timeout=3)
            on = pool.submit(service.activate)
            time.sleep(0.05)
            assert not overlaps
            finish_restore.set()
            off.result(timeout=3)
            on.result(timeout=3)
        assert not overlaps
        assert service.is_active
        assert states == [True, False, True]
    finally:
        finish_restore.set()
        service.stop()
