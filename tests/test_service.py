from pathlib import Path
from veil.service import VeilService


import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from veil import command
from veil.crypto import KeyManager, VaultCrypto
from veil.ipc_server import IPCServer
from veil.vault import Vault

def make_vault(root):
    return Vault(root / "vault.db", VaultCrypto(KeyManager(root)))


def test_service_lifecycle_no_audio_muting(tmp_path):
    srv = VeilService(vault_dir=tmp_path, socket_path=tmp_path / "test.sock", start_ipc=False)
    assert not srv.is_active
    
    # Configure the OFF password. Turning ON stays a single click.
    srv.unlock_guard.set_password('safe test password 123')
    state = srv.toggle()
    assert state is True
    assert srv.is_active is True
    
    # Boss key execution (must not fail or mute sound)
    bk_res = srv.boss_key()
    assert bk_res is True
    assert srv.is_active is True
    
    # Toggle back to inactive
    state = srv.toggle(password='safe test password 123')
    assert state is False
    assert srv.is_active is False
    
    srv.stop()


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
        service.unlock_guard.set_password('safe test password 123')
        service.activate()
        with ThreadPoolExecutor(max_workers=2) as pool:
            off = pool.submit(service.deactivate, password='safe test password 123')
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

