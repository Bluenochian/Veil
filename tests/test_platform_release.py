"""Packaging, validation, and idle-connection tests."""
import gc
import json
import socket
import time
import weakref
import re
from pathlib import Path

from veil import __version__
from veil.classifier import UniversalClassifier
from veil.ipc_server import IPCServer, IPCClient
from veil.paths import icon_directory, browser_extension_directory
from veil.service import VeilService


def test_classifier_does_not_leak_connections_across_instances(tmp_path):
    clf = UniversalClassifier(rules_path=tmp_path / 'rules.json')
    clf.classify_url('https://example.com')
    ref = weakref.ref(clf)
    del clf
    gc.collect()
    assert ref() is None


def test_invalid_persisted_rules_do_not_crash_classifier(tmp_path):
    rules = tmp_path / 'rules.json'
    rules.write_text(json.dumps({'whitelist': [42, None, 'EXAMPLE.com'], 'blacklist': {'a': 1}}))
    clf = UniversalClassifier(rules_path=rules)
    try:
        assert clf.classify_url('https://example.com').is_sensitive is False
        assert clf.whitelist == ['example.com']
        assert clf.blacklist == []
        assert clf.classify_url('https://pornhub.com').is_sensitive is True
    finally:
        clf.close()


def test_long_idle_ipc_connection_remains_connected(tmp_path, monkeypatch):
    monkeypatch.setattr(IPCServer, 'FALLBACK_SOCKET_DIR', tmp_path)
    server = IPCServer(socket_path=tmp_path / 'daemon.sock', on_message_callback=lambda msg, _: {'type': 'echo', 'value': msg['value']})
    server.start()
    client = IPCClient(socket_path=tmp_path / 'daemon.sock')
    try:
        assert client.connect()
        time.sleep(0.6)
        client.send({'type': 'echo', 'value': 'still-alive'})
        assert client.receive(timeout=1.0)['value'] == 'still-alive'
    finally:
        client.close()
        server.stop()


def test_invalid_custom_rules_are_rejected_by_daemon(tmp_path, monkeypatch):
    monkeypatch.setattr(IPCServer, 'FALLBACK_SOCKET_DIR', tmp_path)
    srv = VeilService(vault_dir=tmp_path/'vault',socket_path=tmp_path/'daemon.sock',start_ipc=False)
    try:
        for invalid in (None, 23, [], {}, '', 'x' * 513):
            result = srv._handle_ipc_message({'type':'rules_add', 'rule_type':'black', 'domain':invalid})
            assert result['status'] == 'error'
        assert srv.classifier.blacklist == []
    finally:
        srv.stop()


def test_full_browser_artwork_present_in_source_package():
    assert (icon_directory()/'veil-on-128.png').is_file()
    for browser in ('chrome', 'firefox'):
        ext = browser_extension_directory(browser)
        assert (ext/'manifest.json').is_file()
        assert (ext/'paused.css').is_file()
        assert (ext/'icons'/'icon128.png').is_file()


def test_optional_local_domain_index_is_queried(tmp_path):
    # Classification uses a separately supplied index without bundling third-party data.
    import sqlite3
    from veil.classifier import UniversalClassifier

    db = tmp_path / 'domains.db'
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE domains (domain TEXT NOT NULL)')
        conn.execute('INSERT INTO domains(domain) VALUES (?)', ('example-sensitive.test',))
    clf = UniversalClassifier(db_path=db, rules_path=tmp_path / 'rules.json')
    try:
        result = clf.classify_url('https://example-sensitive.test/neutral')
        assert result.is_sensitive
        assert result.reason.startswith('Database match:'), result
    finally:
        clf.close()



def test_all_release_versions_match():
    """Packagers and browser add-ons should agree on one upstream version."""
    root = Path(__file__).resolve().parent.parent
    version = __version__
    pyproject = (root / "pyproject.toml").read_text()
    setup = (root / "setup.py").read_text()
    debian = (root / "debian/changelog").read_text()
    arch = (root / "packaging/arch/PKGBUILD").read_text()
    rpm = (root / "packaging/rpm/veil.spec").read_text()
    assert re.search(rf'^version = "{re.escape(version)}"$', pyproject, re.M)
    assert f'version="{version}"' in setup
    assert debian.startswith(f"veil ({version}) ")
    assert f"pkgver={version}\n" in arch
    assert f"Version:        {version}\n" in rpm
    for family in ("chrome", "firefox"):
        manifest = json.loads((root / f"browser-extension/{family}/manifest.json").read_text())
        assert manifest["version"] == version
        if family == "firefox":
            assert manifest["background"]["scripts"] == ["background.js"]
        else:
            assert manifest["background"]["service_worker"] == "veil-worker.js"
