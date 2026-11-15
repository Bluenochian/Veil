"""The OFF switch must require authentication at the daemon, not only Qt UI."""
import json
import os
import time
from pathlib import Path

import pytest

from veil.access import AccessDenied, UnlockGuard
from veil.service import VeilService


PASSWORD = "my long local unlock password"
OTHER = "different long password!"


def make_service(tmp_path):
    service = VeilService(
        vault_dir=tmp_path / "config",
        socket_path=tmp_path / "veil.sock",
        start_ipc=False,
    )
    service.profile_manager.conceal_all = lambda _: None
    service.profile_manager.restore_all = lambda: None
    service.sanitize_clipboard = lambda: False
    return service


def test_password_is_salted_scrypt_not_plaintext(tmp_path):
    gate = UnlockGuard(tmp_path / "vault")
    assert not gate.configured
    with pytest.raises(AccessDenied, match="at least 12"):
        gate.set_password("short")
    gate.set_password(PASSWORD)
    assert gate.configured
    raw = gate.path.read_bytes()
    assert PASSWORD.encode() not in raw
    record = json.loads(raw)
    assert record["kdf"] == "scrypt"
    assert len(record["salt"]) > 20
    assert gate.path.stat().st_mode & 0o777 == 0o600
    assert gate.verify(PASSWORD)
    with pytest.raises(AccessDenied, match="Incorrect"):
        gate.verify(OTHER)


def test_cannot_change_existing_password_without_current(tmp_path):
    gate = UnlockGuard(tmp_path / "config")
    gate.set_password(PASSWORD)
    with pytest.raises(AccessDenied):
        gate.set_password(OTHER)
    with pytest.raises(AccessDenied):
        gate.set_password(OTHER, current="wrong")
    assert gate.verify(PASSWORD)
    gate.set_password(OTHER, current=PASSWORD)
    with pytest.raises(AccessDenied):
        gate.verify(PASSWORD)
    assert gate.verify(OTHER)


def test_five_bad_attempts_trigger_delay(tmp_path, monkeypatch):
    gate = UnlockGuard(tmp_path / "config")
    gate.set_password(PASSWORD)
    clock = [100.0]
    with monkeypatch.context() as patch:
        patch.setattr("veil.access.time.monotonic", lambda: clock[0])
        for attempt in range(5):
            with pytest.raises(AccessDenied):
                gate.verify(OTHER)
        with pytest.raises(AccessDenied, match="Too many"):
            gate.verify(PASSWORD)
        clock[0] = 131.0
        assert gate.verify(PASSWORD)


def test_unconfigured_active_shield_cannot_turn_off(tmp_path):
    svc = make_service(tmp_path)
    try:
        svc.activate()
        with pytest.raises(AccessDenied, match="Set an unlock password"):
            svc.deactivate()
        assert svc.is_active
        reply = svc._handle_ipc_message({"type": "deactivate"})
        assert reply["status"] == "error"
        assert reply["active"] is True
        reply = svc._handle_ipc_message({"type": "toggle"})
        assert reply["status"] == "error"
        assert reply["active"] is True
        assert svc._handle_ipc_message({"type": "reveal_all_tabs"})["status"] == "error"
        assert svc.is_active
    finally:
        svc.stop()


def test_ipc_password_setup_and_all_off_routes(tmp_path):
    svc = make_service(tmp_path)
    try:
        assert svc._handle_ipc_message({"type": "unlock_status"}) == {
            "type": "unlock_status", "enabled": False
        }
        assert svc._handle_ipc_message({
            "type": "unlock_set", "new_password": PASSWORD
        })["status"] == "ok"
        assert svc._handle_ipc_message({"type": "unlock_status"})["enabled"]
        assert svc._handle_ipc_message({"type": "toggle"})["active"] is True
        before = svc.vault.get_state("is_active")
        assert before is True
        for op in ("toggle", "deactivate"):
            response = svc._handle_ipc_message({"type": op, "password": OTHER})
            assert response["status"] == "error"
            assert svc.is_active
            assert svc.vault.get_state("is_active") is True
        assert svc._handle_ipc_message({
            "type": "unlock_set", "new_password": OTHER
        })["status"] == "error"
        assert svc._handle_ipc_message({
            "type": "deactivate", "password": PASSWORD
        })["active"] is False
        assert svc._handle_ipc_message({"type": "reveal_all_tabs"})["status"] == "ok"
        assert svc.vault.get_state("is_active") is False
        assert svc._handle_ipc_message({"type": "toggle"})["active"] is True
        assert svc._handle_ipc_message({
            "type": "toggle", "password": PASSWORD
        })["active"] is False
    finally:
        svc.stop()


def test_expired_timer_cannot_disable_active_shield(tmp_path):
    svc = make_service(tmp_path)
    alerts = []
    svc.ipc.broadcast = alerts.append
    try:
        svc.unlock_guard.set_password(PASSWORD)
        svc.activate()
        svc.start_timer(0.01)
        svc.cancel_timer()  # test expiry manually, without waiting
        svc._on_timer_expired()
        assert svc.is_active
        assert svc.vault.get_state("is_active") is True
        assert alerts[-1]["type"] == "unlock_required"
    finally:
        svc.stop()


def test_restart_keeps_password_and_blocks_unverified_deactivation(tmp_path):
    first = make_service(tmp_path)
    first.unlock_guard.set_password(PASSWORD)
    first.activate()
    first.stop()

    restarted = make_service(tmp_path)
    try:
        assert restarted.is_active
        assert restarted.unlock_guard.configured
        with pytest.raises(AccessDenied):
            restarted.deactivate(password=OTHER)
        assert restarted.is_active
        restarted.deactivate(password=PASSWORD)
        assert not restarted.is_active
    finally:
        restarted.stop()


def test_damaged_or_symlinked_password_file_refuses_off(tmp_path):
    gate = UnlockGuard(tmp_path / "config")
    gate.set_password(PASSWORD)
    gate.path.write_text("{}")
    with pytest.raises(AccessDenied, match="damaged"):
        gate.verify(PASSWORD)
    gate.path.unlink()
    target = tmp_path / "outside"
    target.write_text("{}")
    gate.path.symlink_to(target)
    with pytest.raises(AccessDenied, match="symlink"):
        gate.set_password(PASSWORD)
    assert target.read_text() == "{}"



def test_command_cli_prompts_for_off_not_on(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from veil import command

    svc = make_service(tmp_path)

    class LocalClient:
        response = None

        def send(self, message):
            self.response = svc._handle_ipc_message(message)

        def receive(self, timeout=3):
            return self.response

        def close(self):
            return None

    monkeypatch.setattr(command, "get_ipc_client", lambda: LocalClient())
    monkeypatch.setattr(command.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    entered = []
    monkeypatch.setattr(command.getpass, "getpass", lambda _: entered.append(True) or PASSWORD)
    try:
        assert command.cmd_lock(SimpleNamespace(operation="status")) == 0
        assert command.cmd_toggle(SimpleNamespace()) is None
        assert svc.is_active
        assert entered == []  # Turning ON must not ask for the password.
        assert command.cmd_toggle(SimpleNamespace()) == 1  # Must configure the password.
        assert svc.is_active
        svc.unlock_guard.set_password(PASSWORD)
        assert command.cmd_toggle(SimpleNamespace()) is None
        assert not svc.is_active
        assert entered == [True]
    finally:
        svc.stop()


def test_unlock_file_too_large_stays_locked(tmp_path):
    guard = UnlockGuard(tmp_path / "veil")
    guard.set_password("a password nobody should ever guess")
    guard.path.write_bytes(b" " * (guard.MAX_FILE_SIZE + 1))
    with pytest.raises(AccessDenied, match="damaged"):
        guard.verify("a password nobody should ever guess")

