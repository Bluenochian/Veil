#!/usr/bin/env python3
"""Veil's terminal commands and output formatting."""

import sys
import os
import time
import argparse
import getpass
import sqlite3
from pathlib import Path

# Add package root to sys.path
package_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_root not in sys.path:
    sys.path.insert(0, package_root)

# Preserve an existing Wayland/X11 Qt backend setting.
os.environ["KSNI_NO_DBUSMENU"] = "1"

from veil.ipc_server import IPCClient

# ANSI Color Palette - Living Horizon & Deep Violet Theme
AMBER_GOLD = "\033[38;2;245;158;11m"
AMBER_BOLD = "\033[1;38;2;245;158;11m"
PURPLE_BOLD = "\033[1;38;2;192;132;252m"
VIOLET = "\033[38;2;168;85;247m"
LILAC = "\033[38;2;216;180;254m"
WHITE_BOLD = "\033[1;37m"
GREEN_BOLD = "\033[1;32m"
RED_BOLD = "\033[1;31m"
CYAN = "\033[38;2;56;189;248m"
DIM = "\033[2m"
RESET = "\033[0m"


def get_ipc_client():
    client = IPCClient()
    connected = client.connect(timeout=0.6)
    return client if connected else None


def cmd_toggle(args):
    client = get_ipc_client()
    if client:
        client.send({"type": "toggle"})
        res = client.receive(timeout=3.0)
        client.close()
        if not isinstance(res, dict) or not isinstance(res.get("active"), bool):
            print(f"{RED_BOLD}Error: Veil daemon did not confirm its state; no change can be verified.{RESET}", file=sys.stderr)
            return 1
        active = res["active"]
        state_str = f"{PURPLE_BOLD}SHIELD ACTIVE (PROTECTED){RESET}" if active else f"{AMBER_BOLD}STANDBY (RESTORED){RESET}"
        print(f"{VIOLET}✦{RESET} [Veil] State changed: {state_str}")
    else:
        print(f"{RED_BOLD}Error: Veil daemon is not running; protection was not changed. Start `veil tray` first.{RESET}", file=sys.stderr)
        return 1


def cmd_status(args):
    client = get_ipc_client()
    res = None
    if client:
        client.send({"type": "status"})
        res = client.receive(timeout=1.5)
        client.close()
        if not isinstance(res, dict) or not isinstance(res.get("active"), bool):
            print(f"{RED_BOLD}Error: Veil daemon did not respond to status query.{RESET}", file=sys.stderr)
            return 1
        active = res["active"]
        daemon_str = f"{GREEN_BOLD}Running (Active IPC Socket){RESET}"
    else:
        from veil.vault import Vault
        from veil.crypto import VaultCrypto, KeyManager
        vault_dir = Path.home() / ".config" / "veil"
        v = Vault(vault_dir / "vault.db", VaultCrypto(KeyManager(vault_dir)))
        saved_active = bool(v.get_state("is_active", False))
        active = False  # persisted intent is not live protection
        daemon_str = f"{DIM}Offline / Background Daemon Not Running{RESET}"

    if getattr(args, "json", False):
        import json
        out = {
            "daemon_running": client is not None,
            "active": active,
            "reveal_on_demand": res.get("reveal_on_demand", True) if res else True,
            "saved_active": saved_active if client is None else active
        }
        print(json.dumps(out))
        return 0

    state_str = f"{PURPLE_BOLD}SHIELD ACTIVE (PROTECTED){RESET}" if active else f"{AMBER_BOLD}STANDBY (NORMAL){RESET}"
    print(f"\n{AMBER_BOLD}✦ VEIL STATUS{RESET}")
    print(f"{VIOLET}--------------------------------------------------{RESET}")
    print(f"  Daemon Core:     {daemon_str}")
    print(f"  Protection Mode: {state_str}")
    if client is None and saved_active:
        print(f"  Saved Mode:      Active (not enforced until daemon starts)")
    print(f"{VIOLET}--------------------------------------------------{RESET}\n")


def cmd_stats(args):
    client = get_ipc_client()
    counts = {}
    active = False
    uptime = 0
    if client:
        client.send({"type": "stats"})
        res = client.receive(timeout=2.0)
        client.close()
        if res:
            counts = res.get("counts", {})
            active = res.get("active", False)
            uptime = res.get("uptime", 0)
    else:
        from veil.vault import Vault
        from veil.crypto import VaultCrypto, KeyManager
        vault_dir = Path.home() / ".config" / "veil"
        v = Vault(vault_dir / "vault.db", VaultCrypto(KeyManager(vault_dir)))
        counts = v.count_concealed_items()
        active = False  # offline vault state is not active protection

    state_str = f"{PURPLE_BOLD}SHIELD ACTIVE{RESET}" if active else f"{AMBER_BOLD}STANDBY{RESET}"
    uptime_str = f" ({uptime // 60}m {uptime % 60}s)" if uptime > 0 else ""

    print(f"\n{AMBER_BOLD}✦ VEIL VAULT TELEMETRY & CONCEALED ASSETS{RESET}")
    print(f"{VIOLET}=================================================={RESET}")
    print(f"  Engine State:          {state_str}{uptime_str}")
    print(f"{VIOLET}--------------------------------------------------{RESET}")
    print(f"  Concealed Active Tabs: {WHITE_BOLD}{counts.get('tabs', 0):>6}{RESET}")
    print(f"  Vaulted Bookmarks:     {WHITE_BOLD}{counts.get('bookmarks', 0):>6}{RESET}")
    print(f"  Vaulted History URLs:  {WHITE_BOLD}{counts.get('history_urls', 0):>6}{RESET}")
    print(f"  Vaulted History Visits:{WHITE_BOLD}{counts.get('history_visits', 0):>6}{RESET}")
    print(f"  Isolated Search Terms: {WHITE_BOLD}{counts.get('search_terms', 0):>6}{RESET}")
    print(f"{VIOLET}=================================================={RESET}\n")


def cmd_test(args):
    url = args.url
    title = args.title or ""
    from veil.classifier import UniversalClassifier
    clf = UniversalClassifier()
    res = clf.classify(url, title)
    is_sensitive, category, conf, reason, rule, lang = res.is_sensitive, res.category, res.confidence, res.reason, res.matched_rule, res.language


    print(f"\n{AMBER_BOLD}🔍 Classification Diagnostic{RESET}")
    print(f"{VIOLET}=================================================={RESET}")
    print(f"  Target URL:   {LILAC}{url}{RESET}")
    if title:
        print(f"  Page Title:   {title}")
    
    category_labels = {
        "ADULT_EXPLICIT": f"{RED_BOLD}ADULT / EXPLICIT MEDIA 🔞{RESET}",
        "GAMBLING_WAGERING": f"{AMBER_BOLD}GAMBLING / WAGERING / CASINO 🎲{RESET}",
        "SHOCK_VIOLENCE": f"{RED_BOLD}EXTREME SHOCK / VIOLENCE ⚠️{RESET}",
        "ILLICIT_SUBSTANCES": f"{RED_BOLD}ILLICIT SUBSTANCES / NARCOTICS 🚫{RESET}",
        "DECEPTIVE_MALICIOUS": f"{RED_BOLD}DECEPTIVE / MALICIOUS AD 🛡️{RESET}",
        "SAFE": f"{GREEN_BOLD}CLEAN & BENIGN CONTENT ✅{RESET}"
    }
    verdict_badge = category_labels.get(category, f"{CYAN}{category}{RESET}")

    print(f"  Category:     {verdict_badge}")
    print(f"  Concealable:  {RED_BOLD if is_sensitive else GREEN_BOLD}{is_sensitive}{RESET}")
    print(f"  Confidence:   {conf * 100:.1f}%")
    print(f"  Language:     {lang.upper() if lang else 'N/A'}")
    print(f"  Reason:       {reason}")
    if rule:
        print(f"  Matched Pattern: {rule}")
    print(f"{VIOLET}=================================================={RESET}\n")


def cmd_boss_key(args):
    client = get_ipc_client()
    if not client:
        print(f"{RED_BOLD}Error: Veil daemon is not running; boss key cannot protect browser sessions.{RESET}", file=sys.stderr)
        return 1
    client.send({"type": "boss_key"})
    res = client.receive(timeout=3.0)
    client.close()
    if not isinstance(res, dict) or res.get("active") is not True:
        print(f"{RED_BOLD}Error: Veil daemon did not confirm boss-key activation.{RESET}", file=sys.stderr)
        return 1
    print(f"{PURPLE_BOLD}Veil Boss-Key Engaged:{RESET} Privacy shield activated.")
    return 0


def cmd_reveal_all(args):
    client = get_ipc_client()
    if client:
        client.send({"type": "reveal_all_tabs"})
        client.close()
        print(f"{GREEN_BOLD}✓ Restoration broadcast dispatched to all browser sessions.{RESET}")
        return 0
    else:
        print(f"{DIM}Daemon not running. Launch daemon or browser to restore veiled tabs.{RESET}")
        return 1


def cmd_panic(args):
    client = get_ipc_client()
    if not client:
        print(f"{RED_BOLD}Error: Veil daemon is not running; panic protection was not activated.{RESET}", file=sys.stderr)
        return 1
    client.send({"type": "panic"})
    res = client.receive(timeout=4.0)
    client.close()
    if not isinstance(res, dict) or res.get("status") != "panic_executed":
        print(f"{RED_BOLD}Error: Veil daemon did not confirm panic activation.{RESET}", file=sys.stderr)
        return 1
    print(f"\n{RED_BOLD}⚡ [VEIL EMERGENCY PANIC ENGAGED]{RESET}")
    print(f"  ✓ Privacy shield activation confirmed")
    print(f"  Cache cleanup result: {res.get('caches_shredded', {})}\n")
    return 0


def cmd_timer(args):
    client = get_ipc_client()
    if not client:
        print(f"{RED_BOLD}Error: Veil daemon must be running to manage timers.{RESET}")
        return

    if args.cancel:
        client.send({"type": "timer_cancel"})
        client.receive(timeout=2.0)
        client.close()
        print(f"{VIOLET}✦ Timer cancelled.{RESET}")
        return

    mins = args.minutes
    if mins is None or mins <= 0:
        mins = 15.0

    client.send({"type": "timer_set", "minutes": mins})
    client.receive(timeout=2.0)
    client.close()
    print(f"{PURPLE_BOLD}⏱️  Veil Auto-Revert Timer Armed:{RESET} {mins} minutes")


def cmd_sanitize(args):
    client = get_ipc_client()
    if client:
        client.send({"type": "sanitize_clipboard"})
        res = client.receive(timeout=2.0)
        client.close()
    else:
        from veil.service import VeilService
        srv = VeilService()
        cleared = srv.sanitize_clipboard()
        srv.stop()
        res = {"sanitized": cleared, "reason": "Sensitive content purged" if cleared else "Clean clipboard"}

    sanitized = res.get("sanitized", False) if res else False
    reason = res.get("reason", "Unknown") if res else "No response"
    if sanitized:
        print(f"{RED_BOLD}🧹 Clipboard Sanitized:{RESET} {reason}")
    else:
        print(f"{GREEN_BOLD}✓ Clipboard Clean:{RESET} {reason}")


def cmd_sound(args):
    flag = Path.home() / ".config" / "veil" / "sound.enabled"
    flag.parent.mkdir(parents=True, exist_ok=True)
    if args.enable:
        flag.touch()
        print(f"{GREEN_BOLD}✓ Audio Chime Feedback Enabled{RESET}")
    elif args.disable:
        if flag.exists():
            flag.unlink()
        print(f"{LILAC}✓ Audio Chime Feedback Disabled{RESET}")
    else:
        status = "ENABLED" if flag.exists() else "DISABLED"
        print(f"Audio Chime Feedback is currently: {PURPLE_BOLD}{status}{RESET}")


def cmd_autostart(args):
    autostart_dir = Path.home() / ".config" / "autostart"
    autostart_dir.mkdir(parents=True, exist_ok=True)
    desktop_file = autostart_dir / "veil.desktop"

    systemd_dir = Path.home() / ".config" / "systemd" / "user"
    systemd_dir.mkdir(parents=True, exist_ok=True)
    service_file = systemd_dir / "veil.service"

    import shutil
    import shlex
    user_bin = Path.home() / ".local" / "bin" / "veil"
    installed = shutil.which("veil")
    if user_bin.is_file() and os.access(user_bin, os.X_OK):
        launch_target = str(user_bin)
    elif installed:
        launch_target = installed
    else:
        launch_target = f"{shlex.quote(sys.executable)} -m veil.cli"

    if args.enable:
        desktop_content = f"""[Desktop Entry]
Type=Application
Name=Veil
Comment=Veil Linux Privacy & Safe Browsing System
Exec={launch_target} tray
Icon=veil
Terminal=false
Categories=Utility;Security;
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
"""
        desktop_file.write_text(desktop_content, encoding="utf-8")

        service_content = f"""[Unit]
Description=Veil Universal Privacy Daemon
After=graphical-session.target

[Service]
Type=simple
ExecStart={launch_target} tray
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
"""
        service_file.write_text(service_content, encoding="utf-8")
        print(f"{GREEN_BOLD}✓ Desktop autostart and service configured successfully!{RESET}")
        print(f"  + Desktop autostart: {desktop_file}")
        print(f"  + Systemd service:   {service_file}")

    elif args.disable:
        if desktop_file.exists():
            desktop_file.unlink()
        if service_file.exists():
            service_file.unlink()
        print(f"{LILAC}✓ Autostart disabled.{RESET}")
    else:
        status = "ENABLED" if desktop_file.exists() else "DISABLED"
        print(f"Autostart is currently: {PURPLE_BOLD}{status}{RESET}")


def cmd_rules(args):
    client = get_ipc_client()
    if args.add_white:
        dom = args.add_white.strip().lower()
        if client:
            client.send({"type": "rules_add", "rule_type": "white", "domain": dom})
            client.receive(timeout=1.5)
            client.close()
        else:
            from veil.classifier import UniversalClassifier
            UniversalClassifier().add_whitelist_rule(dom)
        print(f"{GREEN_BOLD}✅ Added '{dom}' to Whitelist.{RESET}")
        return

    if args.add_black:
        dom = args.add_black.strip().lower()
        if client:
            client.send({"type": "rules_add", "rule_type": "black", "domain": dom})
            client.receive(timeout=1.5)
            client.close()
        else:
            from veil.classifier import UniversalClassifier
            UniversalClassifier().add_blacklist_rule(dom)
        print(f"{PURPLE_BOLD}🔞 Added '{dom}' to Blacklist.{RESET}")
        return

    if args.remove:
        dom = args.remove.strip().lower()
        if client:
            client.send({"type": "rules_remove", "rule_type": "white", "domain": dom})
            client.receive(timeout=1.5)
            client.send({"type": "rules_remove", "rule_type": "black", "domain": dom})
            client.receive(timeout=1.5)
            client.close()
        else:
            from veil.classifier import UniversalClassifier
            clf = UniversalClassifier()
            clf.remove_whitelist_rule(dom)
            clf.remove_blacklist_rule(dom)
        print(f"🗑️ Removed '{dom}' from custom rules.")
        return

    if client:
        client.send({"type": "rules_get"})
        res = client.receive(timeout=2.0)
        client.close()
        whitelist = res.get("whitelist", []) if res else []
        blacklist = res.get("blacklist", []) if res else []
    else:
        from veil.classifier import UniversalClassifier
        clf = UniversalClassifier()
        whitelist = sorted(list(clf.whitelist))
        blacklist = sorted(list(clf.blacklist))

    print(f"\n{AMBER_BOLD}📋 Veil Custom Privacy Rules{RESET}")
    print(f"{VIOLET}=================================================={RESET}")
    print(f"  {GREEN_BOLD}[WHITELIST - Always Allow]{RESET}")
    if whitelist:
        for w in whitelist:
            print(f"    + {w}")
    else:
        print("    (empty)")

    print(f"\n  {RED_BOLD}[BLACKLIST - Always Conceal]{RESET}")
    if blacklist:
        for b in blacklist:
            print(f"    - {b}")
    else:
        print("    (empty)")
    print(f"{VIOLET}=================================================={RESET}\n")


def cmd_shred(args):
    client = get_ipc_client()
    if client:
        client.send({"type": "shred"})
        res = client.receive(timeout=5.0)
        client.close()
        cleaned = res.get("cleaned", {}) if res else {}
    else:
        from veil.browsers.detector import UniversalProfileManager
        from veil.vault import Vault
        from veil.crypto import VaultCrypto, KeyManager
        vault_dir = Path.home() / ".config" / "veil"
        v = Vault(vault_dir / "vault.db", VaultCrypto(KeyManager(vault_dir)))
        cleaned = UniversalProfileManager(v).shred_all_caches()

    if isinstance(cleaned, dict):
        total = sum(cleaned.values())
        print(f"\n{AMBER_BOLD}🧹 Browser Cache Cleanup{RESET}")
        print(f"{VIOLET}--------------------------------------------------{RESET}")
        for prof, cnt in cleaned.items():
            print(f"  {prof}: {cnt} artifacts shredded")
        print(f"Total purged files: {total}")
        print(f"{VIOLET}--------------------------------------------------{RESET}\n")
    else:
        print(f"{GREEN_BOLD}✓ Shredded {cleaned} cache artifacts.{RESET}")


def cmd_browsers(args):
    from veil.browsers.detector import UniversalProfileManager
    from veil.vault import Vault
    from veil.crypto import VaultCrypto, KeyManager
    vault_dir = Path.home() / ".config" / "veil"
    v = Vault(vault_dir / "vault.db", VaultCrypto(KeyManager(vault_dir)))
    upm = UniversalProfileManager(v)
    
    print(f"\n{AMBER_BOLD}🌐 Detected Browsers & Profiles{RESET}")
    print(f"{VIOLET}=================================================={RESET}")
    if not upm.managers:
        print("  No supported browsers detected on filesystem.")
    for mgr in upm.managers:
        p = mgr.profile
        print(f"  ✦ {WHITE_BOLD}{p.browser_name}{RESET} [{CYAN}{p.browser_type}{RESET}]")
        print(f"    Profile: {p.profile_name}")
        print(f"    Path:    {DIM}{p.path}{RESET}")
    print(f"{VIOLET}=================================================={RESET}\n")


def cmd_install_extension(args):
    from veil.native_host.installer import install_manifests
    import shutil
    user_bin = Path.home() / ".local" / "bin" / "veil-native-host"
    project_bin = Path(package_root) / "bin" / "veil-native-host"
    binary_path = next((p for p in (user_bin, Path(shutil.which("veil-native-host") or ""), project_bin)
                        if p.is_file() and os.access(p, os.X_OK)), None)
    if binary_path is None:
        print("Error: veil-native-host executable was not found; cannot register browser bridge.", file=sys.stderr)
        return 1
    print(f"{PURPLE_BOLD}✦ Installing Native Messaging Host manifests...{RESET}")
    installed = install_manifests(binary_path)
    for p in installed:
        print(f"  {GREEN_BOLD}✓{RESET} {p}")
    if not installed:
        print("No browser profiles were found for native messaging registration.", file=sys.stderr)
        return 1
    from veil.paths import browser_extension_directory
    print(f"\n{GREEN_BOLD}Done! Browser extensions can now bridge with Veil.{RESET}")
    for browser in ("chrome", "firefox"):
        path = browser_extension_directory(browser)
        if path.is_dir():
            print(f"  {browser.capitalize()} unpacked extension: {path}")
    print()


def cmd_export(args):
    dest = Path(args.output or (Path.home() / "veil_backup.veilvault"))
    passphrase = args.passphrase
    if not passphrase and sys.stdin.isatty():
        passphrase = getpass.getpass("Enter encryption passphrase for vault export: ")
    elif not passphrase:
        print("Error: pass --passphrase when running noninteractively.", file=sys.stderr)
        sys.exit(2)

    if not passphrase:
        print("Error: an encryption passphrase is required.", file=sys.stderr)
        sys.exit(2)
    from veil.vault import Vault
    from veil.crypto import VaultCrypto, KeyManager
    vault_dir = Path.home() / ".config" / "veil"
    v = Vault(vault_dir / "vault.db", VaultCrypto(KeyManager(vault_dir)))
    try:
        counts = v.export_vault(dest, passphrase)
    except (ValueError, OSError) as error:
        print(f"{RED_BOLD}Vault export failed: {error}{RESET}", file=sys.stderr)
        return 1
    print(f"{PURPLE_BOLD}🔒 [Veil] Successfully exported encrypted vault to: {dest}{RESET}")
    print(f"   Exported assets: {counts}")


def cmd_import(args):
    src = Path(args.input)
    if not src.exists():
        print(f"{RED_BOLD}❌ Error: Backup file not found: {src}{RESET}", file=sys.stderr)
        sys.exit(1)

    passphrase = args.passphrase
    if not passphrase and sys.stdin.isatty():
        passphrase = getpass.getpass("Enter decryption passphrase for vault import: ")
    elif not passphrase:
        print("Error: pass --passphrase when running noninteractively.", file=sys.stderr)
        sys.exit(2)

    if not passphrase:
        print("Error: a decryption passphrase is required.", file=sys.stderr)
        sys.exit(2)
    from veil.vault import Vault
    from veil.crypto import VaultCrypto, KeyManager
    vault_dir = Path.home() / ".config" / "veil"
    client = get_ipc_client()
    if client:
        client.close()
        print("Error: stop the Veil daemon before importing a vault backup.", file=sys.stderr)
        return 1
    v = Vault(vault_dir / "vault.db", VaultCrypto(KeyManager(vault_dir)))
    try:
        counts = v.import_vault(src, passphrase)
    except (ValueError, OSError) as error:
        print(f"{RED_BOLD}Vault import failed: {error}{RESET}", file=sys.stderr)
        return 1
    except sqlite3.IntegrityError:
        print(f"{RED_BOLD}Vault import refused: overlapping records; existing data was preserved.{RESET}", file=sys.stderr)
        return 1
    print(f"{PURPLE_BOLD}🔓 [Veil] Successfully restored vault from: {src}{RESET}")
    print(f"   Restored assets: {counts}")


def cmd_benchmark(args):
    from veil.classifier import UniversalClassifier
    print(f"{PURPLE_BOLD}⚡ Starting Classification Benchmark (10,000 queries)...{RESET}")
    clf = UniversalClassifier()

    test_queries = [
        ("https://pornhub.com/video/12345", "Adult video"),
        ("https://en.wikipedia.org/wiki/Breast_cancer", "Breast Cancer Research"),
        ("https://stake.com/casino", "Crypto Casino"),
        ("https://github.com/torvalds/linux", "Linux Kernel Repository"),
        ("https://linktr.ee/sexy_babe_onlyfans_xxx", "Adult Links"),
        ("https://search.brave.com/search?q=prostate+cancer+treatment", "Prostate Cancer"),
        ("https://example.jp/view?q=無修正", "Japanese Video"),
        ("https://rotten.com/shock", "Shock Site"),
        ("https://bbc.com/news/world", "World News"),
        ("https://bet365.com/sportsbook", "Sports Betting")
    ]

    iters = 10000
    t0 = time.perf_counter()
    for i in range(iters):
        q, t = test_queries[i % len(test_queries)]
        clf.classify_url(q, t)
    total_time = time.perf_counter() - t0

    avg_us = (total_time / iters) * 1_000_000
    qps = iters / total_time

    print(f"\n{AMBER_BOLD}✦ Benchmark Results:{RESET}")
    print(f"  Total Queries:      {WHITE_BOLD}{iters:,}{RESET}")
    print(f"  Total Elapsed:      {WHITE_BOLD}{total_time:.4f}s{RESET}")
    print(f"  Average Latency:    {GREEN_BOLD}{avg_us:.2f} µs{RESET} ({avg_us/1000:.4f} ms)")
    print(f"  Throughput:         {PURPLE_BOLD}{qps:,.0f} queries/sec{RESET}\n")


def cmd_completions(args):
    shell = args.shell or "bash"
    if shell == "bash":
        print("""# bash completion for veil
_veil() {
    local cur prev words cword
    _init_completion || return
    local commands="toggle status stats test rules shred export import panic boss-key reveal-all timer sanitize sound autostart browsers install-extension benchmark completions tray"
    if [[ $cword -eq 1 ]]; then
        COMPREPLY=($(compgen -W "$commands" -- "$cur"))
    fi
}
complete -F _veil veil
""")
    else:
        print("""#compdef veil
_veil() {
    local -a commands
    commands=(
        'toggle:Toggle Veil privacy shield ON/OFF'
        'status:Show Veil shield and daemon status'
        'stats:Display count breakdown of shielded items'
        'test:Test URL with multi-category classification engine'
        'rules:Manage custom whitelist and blacklist rules'
        'shred:Purge temporary preview & thumbnail caches'
        'export:Export encrypted vault archive'
        'import:Import and restore encrypted vault archive'
        'panic:Instant emergency boss key'
        'boss-key:Instant stealth boss key'
        'reveal-all:Unpause and restore all paused tabs'
        'timer:Auto-revert countdown timer'
        'sanitize:Clean adult and sensitive text from clipboard'
        'sound:Manage audio chime feedback'
        'autostart:Manage autostart configuration'
        'browsers:List all detected browsers and profiles'
        'install-extension:Install native messaging manifests'
        'benchmark:Run classifier performance benchmark'
        'tray:Launch Living Horizon system tray UI'
    )
    _describe -t commands 'veil command' commands
}
""")


def main():
    parser = argparse.ArgumentParser(
        prog="veil",
        description=f"{AMBER_BOLD}Veil Linux Privacy & Safe Browsing System{RESET} - CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  veil toggle                  Toggle privacy shield ON/OFF
  veil status                  Check daemon and shield status
  veil stats                   Display breakdown of shielded items
  veil test <url>              Test URL across safety categories
  veil panic                   Instant emergency boss key (minimize & sanitize)
  veil timer 15                Set 15-minute auto-revert countdown
  veil sanitize                Purge adult/sensitive content from clipboard
  veil sound --enable          Enable audio chime feedback
  veil browsers                List all detected browsers and profiles
  veil install-extension       Register native messaging host for all browsers
  veil autostart --enable      Enable auto-boot on desktop login
"""
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    subparsers.add_parser("toggle", help="Toggle Veil privacy shield ON/OFF")
    status_p = subparsers.add_parser("status", help="Show Veil shield and daemon status")
    status_p.add_argument("--json", action="store_true", help="Output status in JSON format")
    subparsers.add_parser("boss-key", help="Instant stealth boss key")
    subparsers.add_parser("reveal-all", help="Unpause and restore all paused tabs")
    subparsers.add_parser("stats", help="Display count breakdown of shielded items")
    subparsers.add_parser("tray", help="Launch the Living Horizon system tray UI")

    subparsers.add_parser("panic", help="Instant emergency Boss Key (minimize & sanitize)")
    timer_p = subparsers.add_parser("timer", help="Auto-revert countdown timer")
    timer_p.add_argument("minutes", type=float, nargs="?", default=15.0, help="Timer duration in minutes")
    timer_p.add_argument("--cancel", action="store_true", help="Cancel active timer")

    subparsers.add_parser("sanitize", help="Purge sensitive content from clipboard")

    sound_p = subparsers.add_parser("sound", help="Manage audio chime feedback")
    sound_p.add_argument("--enable", action="store_true", help="Enable audio chime")
    sound_p.add_argument("--disable", action="store_true", help="Disable audio chime")

    auto_p = subparsers.add_parser("autostart", help="Manage autostart configuration")
    auto_p.add_argument("--enable", action="store_true", help="Enable autostart on login")
    auto_p.add_argument("--disable", action="store_true", help="Disable autostart on login")

    subparsers.add_parser("browsers", help="List all detected browsers and profiles")
    subparsers.add_parser("install-extension", help="Install native messaging manifests")
    subparsers.add_parser("benchmark", help="Run 10,000 query classifier benchmark")

    comp_p = subparsers.add_parser("completions", help="Generate shell completions")
    comp_p.add_argument("shell", choices=["bash", "zsh"], nargs="?", default="bash")

    test_p = subparsers.add_parser("test", help="Test a URL with classification engine")
    test_p.add_argument("url", help="URL to classify")
    test_p.add_argument("title", nargs="?", default="", help="Optional page title")

    rules_p = subparsers.add_parser("rules", help="Manage custom whitelist and blacklist rules")
    rules_p.add_argument("--list", action="store_true", help="List all rules")
    rules_p.add_argument("--add-white", metavar="DOMAIN", help="Add domain to whitelist")
    rules_p.add_argument("--add-black", metavar="DOMAIN", help="Add domain to blacklist")
    rules_p.add_argument("--remove", metavar="DOMAIN", help="Remove domain from rules")

    subparsers.add_parser("shred", help="Shred Top Sites thumbnails and browser temp caches")

    exp_p = subparsers.add_parser("export", help="Export encrypted vault archive")
    exp_p.add_argument("output", nargs="?", default=None, help="Destination .veilvault file path")
    exp_p.add_argument("-p", "--passphrase", default=None, help="Encryption passphrase")

    imp_p = subparsers.add_parser("import", help="Import encrypted vault archive")
    imp_p.add_argument("input", help="Source .veilvault file path")
    imp_p.add_argument("-p", "--passphrase", default=None, help="Decryption passphrase")

    args = parser.parse_args()

    if not args.subcommand:
        if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
            from veil.tray import main as tray_main
            tray_main()
        else:
            parser.print_help()
        return

    subcmd_map = {
        "toggle": cmd_toggle,
        "status": cmd_status,
        "stats": cmd_stats,
        "test": cmd_test,
        "rules": cmd_rules,
        "shred": cmd_shred,
        "browsers": cmd_browsers,
        "install-extension": cmd_install_extension,
        "export": cmd_export,
        "import": cmd_import,
        "panic": cmd_panic,
        "boss-key": cmd_boss_key,
        "reveal-all": cmd_reveal_all,
        "timer": cmd_timer,
        "sanitize": cmd_sanitize,
        "sound": cmd_sound,
        "autostart": cmd_autostart,
        "benchmark": cmd_benchmark,
        "completions": cmd_completions,
        "tray": lambda a: __import__("veil.tray", fromlist=["main"]).main()
    }

    handler = subcmd_map.get(args.subcommand)
    if handler:
        return handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    sys.exit(main())
