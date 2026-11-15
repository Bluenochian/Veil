"""A few regressions that really don't need to happen twice."""

import ast
import sqlite3
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from veil import command
from veil.access import AccessDenied
from veil.browsers.detector import UniversalProfileManager
from veil.crypto import VaultDecryptionError
from veil.ipc_server import IPCClient
from veil.service import VeilService


def _autostart_args(**values):
    return SimpleNamespace(enable=False, disable=False, start=False, **values)


def test_autostart_uses_one_systemd_unit_and_a_desktop_trigger(tmp_path, monkeypatch):
    import shutil
    import subprocess

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    launcher = tmp_path / ".local/bin/veil"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("#!/bin/sh\n")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("HOME", str(tmp_path))
    commands = []

    def run(argv, **kwargs):
        commands.append(argv)
        assert argv[:2] == ["systemctl", "--user"]
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", run)
    real_which = shutil.which
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/systemctl" if name == "systemctl" else real_which(name))
    monkeypatch.setattr(IPCClient, "connect", lambda self, **kw: False)

    assert command.cmd_autostart(SimpleNamespace(enable=True, disable=False, start=False)) == 0
    unit = (tmp_path / ".config/systemd/user/veil.service").read_text()
    desktop = (tmp_path / ".config/autostart/veil.desktop").read_text()
    assert 'ExecStart="' + str(launcher) + '" tray' in unit
    assert "Restart=on-failure" in unit
    assert "WantedBy=graphical-session.target" in unit
    assert "QT_QPA_PLATFORM" not in unit
    assert "autostart --start" in desktop and '"' + str(launcher) + '"' in desktop
    assert "tray\n" not in desktop  # XDG only starts the unit
    assert ["systemctl", "--user", "enable", "veil.service"] in commands
    assert ["systemctl", "--user", "start", "veil.service"] in commands

    commands.clear()
    assert command.cmd_autostart(SimpleNamespace(enable=False, disable=False, start=True)) == 0
    assert ["systemctl", "--user", "start", "veil.service"] in commands

    commands.clear()
    assert command.cmd_autostart(SimpleNamespace(enable=False, disable=True, start=False)) == 0
    assert ["systemctl", "--user", "disable", "veil.service"] in commands
    assert not (tmp_path / ".config/autostart/veil.desktop").exists()
    assert not (tmp_path / ".config/systemd/user/veil.service").exists()


def test_autostart_desktop_fallback_without_systemd(tmp_path, monkeypatch):
    import shutil
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    launcher = tmp_path / ".local/bin/veil"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("#!/bin/sh\n")
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert command.cmd_autostart(SimpleNamespace(enable=True, disable=False, start=False)) == 0
    desktop = (tmp_path / ".config/autostart/veil.desktop").read_text()
    assert f'Exec="{launcher}" tray' in desktop


def test_a_locked_browser_profile_does_not_stop_others(tmp_path):
    one = SimpleNamespace(
        profile=SimpleNamespace(browser_name="Brave", profile_name="Default"),
        conceal_all=lambda c: (_ for _ in ()).throw(sqlite3.OperationalError("database is locked")),
        restore_all=lambda: (_ for _ in ()).throw(sqlite3.OperationalError("database is locked")),
    )
    two = SimpleNamespace(
        profile=SimpleNamespace(browser_name="Firefox", profile_name="test"),
        conceal_all=lambda c: {"bookmarks": 3, "history": 0, "top_sites": 0},
        restore_all=lambda: {"bookmarks": 2, "history": 0, "top_sites": 0},
    )
    manager = UniversalProfileManager.__new__(UniversalProfileManager)
    manager.managers = [one, two]
    result = manager.conceal_all(object())
    assert result["bookmarks"] == 3
    assert result["errors"] == ["Brave / Default"]
    result = manager.restore_all()
    assert result["bookmarks"] == 2
    assert result["errors"] == ["Brave / Default"]


def test_failed_browser_profile_is_reported_on_state_and_unlock_stays_protected(tmp_path):
    service = VeilService(vault_dir=tmp_path / "vault", socket_path=tmp_path / "s.sock", start_ipc=False)
    events = []
    broadcasts = []
    service.ipc.broadcast = broadcasts.append
    service.on_state_changed = lambda active, msg: events.append((active, msg))
    try:
        service.profile_manager.conceal_all = lambda c: {"errors": ["Brave / Default"]}
        service.profile_manager.restore_all = lambda: {"errors": ["Brave / Default"]}
        service.activate()
        assert service.is_active
        assert broadcasts[-1]["warnings"] == ["Brave / Default"]
        assert "could not be updated" in events[-1][1]
        with pytest.raises(AccessDenied):
            service.deactivate(password=None)
        assert service.is_active
        service.unlock_guard.set_password("a long test password")
        service.deactivate(password="a long test password")
        assert not service.is_active
        assert broadcasts[-1]["warnings"] == ["Brave / Default"]
        assert "could not be restored" in events[-1][1]
    finally:
        service.stop()


def test_failed_vault_state_write_does_not_claim_a_toggle(tmp_path):
    service = VeilService(vault_dir=tmp_path / "vault", socket_path=tmp_path / "s.sock", start_ipc=False)
    orig = service.vault.set_state
    try:
        service.vault.set_state = lambda *a, **kw: (_ for _ in ()).throw(OSError("disk full"))
        with pytest.raises(OSError):
            service.activate()
        assert not service.is_active
        service.vault.set_state = orig
        service.activate()
        service.unlock_guard.set_password("a long test password")
        service.vault.set_state = lambda *a, **kw: (_ for _ in ()).throw(OSError("disk full"))
        with pytest.raises(OSError):
            service.deactivate(password="a long test password")
        assert service.is_active
    finally:
        service.vault.set_state = orig
        service.stop()


def test_panel_toggle_debounce_and_password_prompt_without_qt(tmp_path):
    # Execute the real method independently: CI machines don't have a desktop.
    root = Path(__file__).resolve().parents[1]
    tree = ast.parse((root / "veil/tray.py").read_text())
    imports_time = any(isinstance(n, ast.Import) and any(alias.name == "time" for alias in n.names) for n in tree.body)
    assert imports_time
    tray_class = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "VeilTrayApp")
    fn = next(n for n in tray_class.body if isinstance(n, ast.FunctionDef) and n.name == "_do_toggle")
    code = compile(ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[])), "tray-toggle", "exec")
    clock = SimpleNamespace(now=5.0)
    mocked_time = SimpleNamespace(monotonic=lambda: clock.now)
    calls = []
    service = SimpleNamespace(is_active=False, unlock_guard=SimpleNamespace(configured=True))

    def activate():
        calls.append("on")
        service.is_active = True

    def deactivate(password):
        calls.append(("off", password))
        service.is_active = False

    service.activate = activate
    service.deactivate = deactivate
    widgets = SimpleNamespace(
        QInputDialog=SimpleNamespace(getText=lambda *a, **kw: ("secret", True)),
        QLineEdit=SimpleNamespace(EchoMode=SimpleNamespace(Password=42)),
        QMessageBox=SimpleNamespace(warning=lambda *a: calls.append("warning")),
    )
    namespace = {"time": mocked_time, "QtWidgets": widgets, "AccessDenied": AccessDenied}
    exec(code, namespace)
    fake_app = SimpleNamespace(service=service, _play_sound=lambda state: None)
    toggle = lambda: namespace["_do_toggle"](fake_app)
    toggle()
    clock.now += 0.1
    toggle()  # duplicated Plasma activation
    assert calls == ["on"]
    clock.now += 0.5
    toggle()
    assert calls == ["on", ("off", "secret")]
    clock.now += 0.1
    toggle()
    assert calls == ["on", ("off", "secret")]


def test_encrypted_restore_failure_keeps_veil_on(tmp_path):
    service = VeilService(vault_dir=tmp_path / "vault", socket_path=tmp_path / "s.sock", start_ipc=False)
    events = []
    service.ipc.broadcast = events.append
    try:
        service.unlock_guard.set_password("a long test password")
        service.activate()
        prior_events = len(events)
        service.profile_manager.restore_all = lambda: (_ for _ in ()).throw(
            VaultDecryptionError("bad key")
        )
        with pytest.raises(VaultDecryptionError):
            service.deactivate(password="a long test password")
        assert service.is_active
        assert service.vault.get_state("is_active") is True
        assert len(events) == prior_events  # No OFF signal escaped.
    finally:
        service.stop()


def test_encrypted_conceal_failure_still_notifies_connected_extensions(tmp_path):
    service = VeilService(vault_dir=tmp_path / "vault", socket_path=tmp_path / "s.sock", start_ipc=False)
    events = []
    service.ipc.broadcast = events.append
    try:
        service.profile_manager.conceal_all = lambda classifier: (_ for _ in ()).throw(
            VaultDecryptionError("bad key")
        )
        with pytest.raises(VaultDecryptionError):
            service.activate()
        assert service.is_active
        assert service.vault.get_state("is_active") is True
        assert events[-1]["active"] is True
        assert events[-1]["warnings"] == ["Encrypted browser records couldn't be read"]
    finally:
        service.stop()
