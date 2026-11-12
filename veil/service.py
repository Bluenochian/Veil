"""The desktop service owns Veil's state, vault operations and IPC.

Toggles and recovery writes are serialized here so we don't leave tabs
half-concealed when another request comes in.
"""

import os
import math
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Any
from veil.classifier import UniversalClassifier
from veil.crypto import VaultCrypto, KeyManager, VaultDecryptionError
from veil.vault import Vault
from veil.browsers.detector import UniversalProfileManager
from veil.ipc_server import IPCServer


class VeilService:
    def __init__(self, vault_dir: Path | None = None, socket_path: Path | None = None, start_ipc: bool = True):
        self.vault_dir = Path(vault_dir) if vault_dir else (Path.home() / ".config" / "veil")
        self.km = KeyManager(self.vault_dir)
        self.crypto = VaultCrypto(self.km)
        self.vault = Vault(self.vault_dir / "vault.db", self.crypto)
        self.classifier = UniversalClassifier()
        self.profile_manager = UniversalProfileManager(self.vault)

        # Toggles and vault writes need to happen in order. Races get wierd fast.
        self._state_lock = threading.RLock()

        self.is_active: bool = bool(self.vault.get_state("is_active", False))
        self.activated_at: float | None = time.time() if self.is_active else None

        # Timed privacy countdown
        self._timer: threading.Timer | None = None
        self._timer_end: float | None = None

        self.on_state_changed: Callable[[bool, str], None] | None = None
        self.on_clipboard_query: Callable[[], str] | None = None
        self.on_clipboard_clear: Callable[[], None] | None = None

        # Start IPC Server
        self.ipc = IPCServer(socket_path=socket_path, on_message_callback=self._handle_ipc_message)
        if start_ipc:
            self.ipc.start()

        self._watcher_running = True
        self._screensaver_proc = None
        self._screensaver_thread = threading.Thread(target=self._screensaver_watcher_loop, daemon=True, name="veil-screensaver")
        self._screensaver_thread.start()

    def _screensaver_watcher_loop(self):
        """Monitors FreeDesktop / KDE ScreenSaver locks to auto-veil if configured."""
        try:
            p = subprocess.Popen(
                ["gdbus", "monitor", "-y", "-d", "org.freedesktop.ScreenSaver"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True
            )
            self._screensaver_proc = p
            while self._watcher_running and p.stdout:
                line = p.stdout.readline()
                if not line:
                    break
                if "ActiveChanged" in line and "true" in line.lower():
                    auto_lock_flag = self.vault_dir / "autolock.enabled"
                    if auto_lock_flag.exists() and not self.is_active:
                        self.activate()
        except Exception:
            pass

    def _handle_ipc_message(self, msg: dict, client_sock: Any = None) -> dict | None:
        with self._state_lock:
            try:
                return self._dispatch_ipc_message(msg, client_sock)
            except VaultDecryptionError:
                # Keep the socket alive and let the extension display the failure.
                # Do not delete any recovery records on an authentication error.
                operation = msg.get("type") if isinstance(msg, dict) else None
                response_type = {
                    "resolve_tab": "tab_resolve",
                    "resolve_tabs": "tabs_resolve",
                    "list_live_bookmarks": "live_bookmarks",
                }.get(operation, "error")
                return {
                    "type": response_type,
                    "status": "error",
                    "error": "Encrypted recovery data could not be decrypted. Vault records were kept.",
                }

    def _state_payload(self):
        return {
            "type": "state", "active": self.is_active,
            "reveal_on_demand": self._reveal_on_demand(),
            "rules": {"whitelist": self.classifier.whitelist, "blacklist": self.classifier.blacklist},
        }

    def _dispatch_ipc_message(self, msg: dict, client_sock: Any = None) -> dict | None:
        if not isinstance(msg, dict):
            return {"error": "invalid_message"}
        mtype = msg.get("type")
        if mtype in ("get_state", "native_host_connected"):
            return self._state_payload()


        if mtype == "status":
            counts = self.vault.count_concealed_items()
            return {
                "active": self.is_active,
                "reveal_on_demand": self._reveal_on_demand(),
                "uptime": int(time.time() - self.activated_at) if (self.is_active and self.activated_at) else 0,
                "counts": counts,
                "timer_remaining": int(self._timer_end - time.time()) if self._timer_end else None
            }

        elif mtype == "toggle":
            new_state = self.toggle()
            return self._state_payload()

        elif mtype == "activate":
            self.activate()
            return self._state_payload()

        elif mtype == "deactivate":
            self.deactivate()
            return self._state_payload()

        elif mtype == "panic":
            return self.panic()

        elif mtype == "boss_key":
            self.boss_key()
            return self._state_payload()

        elif mtype == "stats":
            return {"counts": self.vault.count_concealed_items(), "active": self.is_active}

        elif mtype in ("classify", "test_url"):
            url = msg.get("url", "")
            title = msg.get("title", "")
            # lru_cache still needs hashable arguments. Yep, even here.
            if not isinstance(url, str):
                url = ""
            if not isinstance(title, str):
                title = ""
            res = self.classifier.classify_url(url, title)
            return {
                "is_sensitive": res.is_sensitive,
                "is_adult": res.is_adult,
                "category": res.category,
                "confidence": res.confidence,
                "reason": res.reason,
                "rule": res.matched_rule,
                "language": res.language
            }

        elif mtype == "reveal_all_tabs":
            self.ipc.broadcast({"type": "reveal_all_tabs"})
            return {"status": "ok"}

        elif mtype == "timer_set":
            try:
                mins = float(msg.get("minutes", 15.0))
            except (TypeError, ValueError):
                return {"status": "error", "error": "Invalid timer duration"}
            if not 0 < mins <= 1440 or not math.isfinite(mins):
                return {"status": "error", "error": "Timer must be between 0 and 1440 minutes"}
            self.start_timer(mins)
            return {"status": "timer_set", "minutes": mins}

        elif mtype == "timer_cancel":
            self.cancel_timer()
            return {"status": "timer_cancelled"}

        elif mtype == "sanitize_clipboard":
            cleaned = self.sanitize_clipboard()
            return {
                "sanitized": cleaned,
                "reason": "Sensitive clipboard content neutralized" if cleaned else "Clipboard was clean"
            }

        elif mtype == "shred":
            cleaned = self.profile_manager.shred_all_caches()
            return {"cleaned": cleaned}

        elif mtype == "rules_get":
            return {
                "whitelist": self.classifier.whitelist,
                "blacklist": self.classifier.blacklist
            }

        elif mtype == "rules_add":
            rtype = msg.get("rule_type")
            dom = msg.get("domain", "")
            if rtype not in ("white", "black") or not isinstance(dom, str) or not 0 < len(dom.strip()) <= 512:
                return {"status": "error", "error": "Invalid pattern"}
            if rtype == "white":
                self.classifier.add_whitelist_rule(dom)
            elif rtype == "black":
                self.classifier.add_blacklist_rule(dom)
            self.ipc.broadcast(self._state_payload())
            return {"status": "ok"}

        elif mtype == "rules_remove":
            rtype = msg.get("rule_type")
            dom = msg.get("domain", "")
            if rtype not in ("white", "black") or not isinstance(dom, str) or not 0 < len(dom.strip()) <= 512:
                return {"status": "error", "error": "Invalid pattern"}
            if rtype == "white":
                self.classifier.remove_whitelist_rule(dom)
            elif rtype == "black":
                self.classifier.remove_blacklist_rule(dom)
            self.ipc.broadcast(self._state_payload())
            return {"status": "ok"}


        elif mtype == "vault_tab":
            profile = self._live_profile(msg.get("profile"))
            token, url = msg.get("token"), msg.get("url")
            if not self.is_active or not profile or not isinstance(token, str) or not isinstance(url, str):
                return {"type": "tab_vault_ack", "status": "error"}
            import re
            from urllib.parse import urlsplit
            try:
                parsed = urlsplit(url)
                valid_url = parsed.scheme in ("http", "https") and bool(parsed.hostname)
            except ValueError:
                valid_url = False
            if not re.fullmatch(r"[a-f0-9-]{36}", token) or not valid_url:
                return {"type": "tab_vault_ack", "status": "error"}
            self.vault.store_tab(profile, token, url)
            return {"type": "tab_vault_ack", "status": "ok"}

        elif mtype == "vault_tabs":
            # Bulk acknowledgement is all-or-nothing: never navigate before
            # every URL has been encrypted and the SQLite transaction committed.
            profile, entries = self._live_profile(msg.get("profile")), msg.get("tabs")
            if not self.is_active or not profile or not isinstance(entries, list) or not 0 < len(entries) <= 128:
                return {"type": "tabs_vault_ack", "status": "error"}
            import re
            from urllib.parse import urlsplit
            seen = set()
            batch = []
            for entry in entries:
                if not isinstance(entry, dict):
                    return {"type": "tabs_vault_ack", "status": "error"}
                token, url = entry.get("token"), entry.get("url")
                if not isinstance(token, str) or not re.fullmatch(r"[a-f0-9-]{36}", token) or token in seen:
                    return {"type": "tabs_vault_ack", "status": "error"}
                if not isinstance(url, str) or len(url) > 8192:
                    return {"type": "tabs_vault_ack", "status": "error"}
                try:
                    parsed = urlsplit(url)
                    valid = parsed.scheme in ("http", "https") and bool(parsed.hostname)
                except ValueError:
                    valid = False
                if not valid:
                    return {"type": "tabs_vault_ack", "status": "error"}
                seen.add(token)
                batch.append((token, url))
            self.vault.store_tabs(profile, batch)
            return {"type": "tabs_vault_ack", "status": "ok", "tokens": [token for token, _ in batch]}

        elif mtype == "resolve_tabs":
            profile, tokens = self._live_profile(msg.get("profile")), msg.get("tokens")
            if self.is_active or not profile or not self._valid_tab_tokens(tokens):
                return {"type": "tabs_resolve", "status": "error"}
            return {"type": "tabs_resolve", "status": "ok", "tabs": self.vault.retrieve_tabs(profile, tokens)}

        elif mtype == "clear_tabs":
            profile, tokens = self._live_profile(msg.get("profile")), msg.get("tokens")
            if self.is_active or not profile or not self._valid_tab_tokens(tokens):
                return {"type": "tabs_clear_ack", "status": "error"}
            self.vault.clear_tabs(profile, tokens)
            return {"type": "tabs_clear_ack", "status": "ok"}

        elif mtype == "resolve_tab":
            profile = self._live_profile(msg.get("profile"))
            token = msg.get("token")
            if self.is_active or not profile or not isinstance(token, str):
                return {"type": "tab_resolve", "status": "error"}
            url = self.vault.retrieve_tab(profile, token)
            return {"type": "tab_resolve", "status": "ok" if url else "error", "url": url}

        elif mtype == "clear_tab":
            profile = self._live_profile(msg.get("profile"))
            token = msg.get("token")
            if not profile or self.is_active or not isinstance(token, str):
                return {"type": "tab_clear_ack", "status": "error"}
            removed = self.vault.clear_tab(profile, token)
            return {"type": "tab_clear_ack", "status": "ok" if removed else "not_found"}

        elif mtype == "vault_bookmark":
            profile = self._live_profile(msg.get("profile"))
            item = msg.get("item")
            if (not profile or not isinstance(item, dict)
                    or not isinstance(item.get("url"), str) or not item["url"]
                    or not isinstance(item.get("id"), (str, int)) or not str(item["id"])
                    or not isinstance(item.get("title", ""), str)
                    or not isinstance(item.get("parentId", ""), (str, int))):
                return {"type": "vault_ack", "status": "error", "error": "Invalid bookmark or profile"}
            try:
                index = int(item.get("index") or 0)
            except (ValueError, TypeError, OverflowError):
                return {"type": "vault_ack", "status": "error", "error": "Invalid bookmark index"}
            if not 0 <= index <= 2**31 - 1:
                return {"type": "vault_ack", "status": "error", "error": "Invalid bookmark index"}
            if not self.is_active:
                return {"type": "vault_ack", "status": "error", "error": "Veil is inactive"}
            res = self.classifier.classify_url(item["url"], item.get("title", ""))
            # The extension checks again for the UI; the daemon gets the final say on vault writes.
            if not res.is_sensitive:
                return {"type": "vault_ack", "status": "error", "error": "Not classified sensitive"}
            vault_id = self.vault.store_live_bookmark(
                profile=profile, guid=str(item["id"]), parent_guid=str(item.get("parentId", "")),
                original_index=index, url=item["url"],
                title=item.get("title", ""), date_added=str(item.get("dateAdded", "")),
            )
            return {"type": "vault_ack", "status": "ok", "vault_id": vault_id}

        elif mtype == "unstage_bookmark":
            # Undo a staged snapshot if the browser confirmed it never deleted
            # that bookmark (e.g. it changed while native IPC was pending).
            profile = self._live_profile(msg.get("profile"))
            vault_id = msg.get("vault_id")
            if not self.is_active or not profile:
                return {"type": "unstage_ack", "status": "error"}
            cleared = self.vault.clear_bookmark_entry(profile, vault_id)
            return {"type": "unstage_ack", "status": "ok" if cleared else "error"}

        elif mtype == "list_live_bookmarks":
            profile = self._live_profile(msg.get("profile"))
            if not profile or self.is_active:
                return {"type": "live_bookmarks", "status": "error", "bookmarks": []}
            return {"type": "live_bookmarks", "status": "ok", "bookmarks": self.vault.retrieve_bookmarks(profile)}

        elif mtype == "bookmark_restored":
            profile = self._live_profile(msg.get("profile"))
            if not profile or self.is_active:
                return {"type": "bookmark_restored_ack", "status": "error"}
            removed = self.vault.clear_bookmark_entry(profile, msg.get("vault_id"))
            return {"type": "bookmark_restored_ack", "status": "ok" if removed else "error"}

        elif mtype == "vault_history":
            # The browser history API cannot preserve visit timestamps or transitions.
            # Do not acknowledge live history removal as safe.
            return {"status": "unsupported", "error": "Lossless live-history restoration is unavailable"}

        return {"error": "unknown_command"}

    @staticmethod
    def _valid_tab_tokens(tokens):
        import re
        return (isinstance(tokens, list) and 0 < len(tokens) <= 128 and
                all(isinstance(t, str) and re.fullmatch(r"[a-f0-9-]{36}", t) for t in tokens) and
                len(set(tokens)) == len(tokens))

    @staticmethod
    def _live_profile(value):
        # Profile IDs are random for a reason. Dont restore into somebody else's profile.
        import re
        if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9-]{36}", value):
            return None
        return "LiveBrowser:" + value

    def _reveal_on_demand(self):
        return not (self.vault_dir / "reveal_on_demand.disabled").exists()

    def toggle(self) -> bool:
        with self._state_lock:
            if self.is_active:
                self.deactivate()
            else:
                self.activate()
            return self.is_active

    def activate(self):
        with self._state_lock:
            if self.is_active:
                return
            self.is_active = True
            self.activated_at = time.time()
            self.vault.set_state("is_active", True)
            self.profile_manager.conceal_all(self.classifier)
            self.ipc.broadcast(self._state_payload())
            self.sanitize_clipboard()
            if self.on_state_changed:
                self.on_state_changed(True, "Shield Active")

    def deactivate(self):
        with self._state_lock:
            if not self.is_active:
                return
            self.is_active = False
            self.activated_at = None
            self.vault.set_state("is_active", False)
            if self._timer:
                self._timer.cancel()
                self._timer = None
                self._timer_end = None
            self.profile_manager.restore_all()
            self.ipc.broadcast(self._state_payload())
            if self.on_state_changed:
                self.on_state_changed(False, "Standby")

    def sanitize_clipboard(self) -> bool:
        """Clear matching content from the clipboard."""
        text = ""
        if self.on_clipboard_query:
            try:
                text = self.on_clipboard_query()
            except Exception:
                pass
        else:
            try:
                res = subprocess.run(["wl-paste", "-n"], capture_output=True, text=True, timeout=0.4)
                if res.returncode == 0:
                    text = res.stdout
                else:
                    res_x = subprocess.run(["xclip", "-selection", "clipboard", "-o"], capture_output=True, text=True, timeout=0.4)
                    if res_x.returncode == 0:
                        text = res_x.stdout
            except Exception:
                pass

        if text and self.classifier.classify_url(text).is_sensitive:
            if self.on_clipboard_clear:
                self.on_clipboard_clear()
            else:
                try:
                    subprocess.run(["wl-copy", "--clear"], capture_output=True, timeout=0.4)
                except Exception:
                    try:
                        subprocess.run(["xclip", "-selection", "clipboard", "/dev/null"], capture_output=True, timeout=0.4)
                    except Exception:
                        pass
            return True
        return False

    def boss_key(self) -> bool:
        """Instant stealth activation: activates Veil, sanitizes clipboard, pauses dunst."""
        if not self.is_active:
            self.activate()
        self.sanitize_clipboard()
        try:
            subprocess.run(["dunstctl", "set-paused", "true"], capture_output=True, timeout=0.5)
        except Exception:
            pass
        return True

    def panic(self) -> dict:
        """Emergency panic mode: activates Veil, minimizes to desktop, sanitizes clipboard, shreds caches."""
        self.activate()
        try:
            subprocess.run(
                ["qdbus", "org.kde.kglobalaccel", "/component/kwin", "org.kde.kglobalaccel.Component.invokeShortcut", "Show Desktop"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=0.8
            )
        except Exception:
            pass
        self.sanitize_clipboard()
        shredded = self.profile_manager.shred_all_caches()
        return {"status": "panic_executed", "caches_shredded": shredded}

    def start_timer(self, minutes: float):
        if not math.isfinite(minutes) or not 0 < minutes <= 1440:
            raise ValueError("Timer must be between 0 and 1440 minutes")
        if self._timer:
            self._timer.cancel()
        if not self.is_active:
            self.activate()
        seconds = max(10, int(minutes * 60))
        self._timer_end = time.time() + seconds
        self._timer = threading.Timer(seconds, self._on_timer_expired)
        self._timer.daemon = True
        self._timer.start()

    def cancel_timer(self):
        if self._timer:
            self._timer.cancel()
            self._timer = None
            self._timer_end = None

    def _on_timer_expired(self):
        with self._state_lock:
            self._timer = None
            self._timer_end = None
            if self.is_active:
                self.deactivate()

    def stop(self):
        self._watcher_running = False
        proc = self._screensaver_proc
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass
        self.cancel_timer()
        self.ipc.stop()
        self.classifier.close()
