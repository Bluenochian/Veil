"""Firefox-family profile helpers.

The old places.sqlite editing path stays behind the experimental switch.
Normal browser actions go through the extension.
"""

import os
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Any
from veil.browsers.base import BaseBrowserManager, BrowserProfile


class FirefoxBrowserManager(BaseBrowserManager):
    def __init__(self, profile: BrowserProfile, vault):
        super().__init__(profile, vault)
        self.profile_dir = profile.path
        self.browser_name = profile.browser_name
        self.profile_name = profile.profile_name

        self.places_path = self.profile_dir / "places.sqlite"
        self.favicons_path = self.profile_dir / "favicons.sqlite"

    def is_database_locked(self) -> bool:
        if not self.places_path.exists():
            return False
        conn = None
        try:
            conn = sqlite3.connect(str(self.places_path), timeout=0.2)
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("ROLLBACK")
            return False
        except Exception:
            return True
        finally:
            if conn:
                try: conn.close()
                except Exception: pass

    def _offline_edit_permitted(self) -> bool:
        # The old DB rewrite path stays off in safe mode. Running browsers dont play nice with it.
        # They can otherwise race running browsers and corrupt browsing data.
        return os.environ.get("VEIL_EXPERIMENTAL_OFFLINE_DB") == "1" and not self.is_database_locked()

    def _create_backup(self, file_path: Path) -> Path | None:
        if not file_path.exists():
            return None
        # Never create plaintext snapshots of sensitive browsing databases.
        # Keep writes transactional so a half-finished change doesnt stick.
        return None

    def _restore_backup(self, backup_path: Path | None, target_path: Path):
        if backup_path and backup_path.exists():
            try:
                shutil.copy2(backup_path, target_path)
            except Exception:
                pass

    def checkpoint_sqlite_wal(self) -> int:
        if self.places_path.exists():
            try:
                conn = sqlite3.connect(str(self.places_path), timeout=1.5)
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                conn.close()
                return 1
            except Exception:
                pass
        return 0

    def conceal_all(self, classifier) -> dict:
        if not self._offline_edit_permitted():
            return {"bookmarks": 0, "history": 0, "top_sites": 0}
        if not self.places_path.exists() or self.is_database_locked():
            return {"bookmarks": 0, "history": 0, "top_sites": 0}

        self.checkpoint_sqlite_wal()
        backup_path = self._create_backup(self.places_path)
        conn = None
        try:
            conn = sqlite3.connect(str(self.places_path), timeout=3.0)
            cur = conn.cursor()

            cur.execute("SELECT id, url, title, visit_count, typed, frecency, last_visit_date, guid FROM moz_places")
            places = cur.fetchall()

            sensitive_place_ids = []
            for row in places:
                p_id, u_url, u_title, v_cnt, typed, frec, last_v, guid = row
                res = classifier.classify_url(u_url, u_title or "")
                if res.is_sensitive:
                    sensitive_place_ids.append((p_id, u_url, u_title, v_cnt, typed, frec, last_v, guid, res.category))

            if not sensitive_place_ids:
                conn.close()
                return {"bookmarks": 0, "history": 0, "top_sites": 0}

            p_ids = [str(x[0]) for x in sensitive_place_ids]
            placeholders = ",".join("?" for _ in p_ids)

            cur.execute(f"SELECT id, type, fk, parent, position, title, dateAdded, lastModified, guid FROM moz_bookmarks WHERE fk IN ({placeholders})", p_ids)
            bms = cur.fetchall()

            cur.execute(f"SELECT id, from_visit, place_id, visit_date, visit_type, session FROM moz_historyvisits WHERE place_id IN ({placeholders})", p_ids)
            visits = cur.fetchall()

            self.vault.store_firefox_places(
                profile=f"{self.browser_name}:{self.profile_name}",
                places=sensitive_place_ids,
                bookmarks=bms,
                visits=visits
            )

            cur.execute("BEGIN TRANSACTION")
            cur.execute(f"DELETE FROM moz_bookmarks WHERE fk IN ({placeholders})", p_ids)
            cur.execute(f"DELETE FROM moz_historyvisits WHERE place_id IN ({placeholders})", p_ids)
            cur.execute(f"DELETE FROM moz_places WHERE id IN ({placeholders})", p_ids)
            conn.commit()
            conn.close()

            return {"bookmarks": len(bms), "history": len(sensitive_place_ids) - len(bms), "top_sites": 0}
        except Exception:
            if conn:
                try: conn.close()
                except Exception: pass
            self._restore_backup(backup_path, self.places_path)
            return {"bookmarks": 0, "history": 0, "top_sites": 0}

    def restore_all(self) -> dict:
        if not self._offline_edit_permitted():
            return {"bookmarks": 0, "history": 0, "top_sites": 0}
        if not self.places_path.exists() or self.is_database_locked():
            return {"bookmarks": 0, "history": 0, "top_sites": 0}

        stored = self.vault.retrieve_firefox_places(profile=f"{self.browser_name}:{self.profile_name}")
        if not stored.get("places"):
            return {"bookmarks": 0, "history": 0, "top_sites": 0}

        backup_path = self._create_backup(self.places_path)
        conn = None
        try:
            conn = sqlite3.connect(str(self.places_path), timeout=3.0)
            cur = conn.cursor()
            cur.execute("BEGIN TRANSACTION")

            for p in stored["places"]:
                cur.execute(
                    "INSERT OR REPLACE INTO moz_places (id, url, title, visit_count, typed, frecency, last_visit_date, guid) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (p["id"], p["url"], p["title"], p["visit_count"], p["typed"], p["frecency"], p["last_visit_date"], p["guid"])
                )

            for b in stored.get("bookmarks", []):
                cur.execute(
                    "INSERT OR REPLACE INTO moz_bookmarks (id, type, fk, parent, position, title, dateAdded, lastModified, guid) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (b["id"], b["type"], b["fk"], b["parent"], b["position"], b["title"], b["dateAdded"], b["lastModified"], b["guid"])
                )

            for v in stored.get("visits", []):
                cur.execute(
                    "INSERT OR REPLACE INTO moz_historyvisits (id, from_visit, place_id, visit_date, visit_type, session) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (v["id"], v["from_visit"], v["place_id"], v["visit_date"], v["visit_type"], v["session"])
                )

            conn.commit()
            conn.close()

            self.vault.clear_firefox_places(profile=f"{self.browser_name}:{self.profile_name}")
            return {"bookmarks": len(stored.get("bookmarks", [])), "history": len(stored["places"]), "top_sites": 0}
        except Exception:
            if conn:
                try: conn.close()
                except Exception: pass
            self._restore_backup(backup_path, self.places_path)
            return {"bookmarks": 0, "history": 0, "top_sites": 0}

    def shred_caches(self) -> int:
        if not self._offline_edit_permitted():
            return 0
        shredded = 0
        cache_targets = [
            self.profile_dir / "jumpListCache",
            self.profile_dir / "thumbnails"
        ]
        for t in cache_targets:
            if t.exists():
                try:
                    if t.is_file(): t.unlink()
                    else: shutil.rmtree(t, ignore_errors=True)
                    shredded += 1
                except Exception:
                    pass
        return shredded
