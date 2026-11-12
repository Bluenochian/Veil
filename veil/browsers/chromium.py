"""Chromium-family profile helpers.

Direct database edits are experimental. The extension handles normal
live tab and bookmark changes.
"""

import os
import shutil
import sqlite3
import json
import tempfile
from pathlib import Path
from typing import Any
from veil.browsers.base import BaseBrowserManager, BrowserProfile


class ChromiumBrowserManager(BaseBrowserManager):
    def __init__(self, profile: BrowserProfile, vault):
        super().__init__(profile, vault)
        self.profile_dir = profile.path
        self.browser_name = profile.browser_name
        self.profile_name = profile.profile_name

        self.bookmarks_path = self.profile_dir / "Bookmarks"
        self.history_path = self.profile_dir / "History"
        self.shortcuts_path = self.profile_dir / "Shortcuts"
        self.top_sites_path = self.profile_dir / "Top Sites"

    def is_database_locked(self) -> bool:
        """Check if the browser still has a write lock. Don't race it."""
        if not self.history_path.exists():
            return False
        conn = None
        try:
            conn = sqlite3.connect(str(self.history_path), timeout=0.2)
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("ROLLBACK")
            return False
        except Exception:
            return True
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def _offline_edit_permitted(self) -> bool:
        # Legacy database rewriters are experimental and disabled in safe mode.
        # They can otherwise race running browsers and corrupt browsing data.
        return os.environ.get("VEIL_EXPERIMENTAL_OFFLINE_DB") == "1" and not self.is_database_locked()

    def _create_backup(self, file_path: Path) -> Path | None:
        if not file_path.exists():
            return None
        # Never create plaintext snapshots of sensitive browsing databases.
        # Transactions and atomic JSON replacement provide rollback semantics.
        return None

    def _restore_backup(self, backup_path: Path | None, target_path: Path):
        if backup_path and backup_path.exists():
            try:
                shutil.copy2(backup_path, target_path)
            except Exception:
                pass

    def checkpoint_sqlite_wal(self) -> int:
        """Checkpoint the WAL before touching the offline databse."""
        checkpointed = 0
        for db_file in [self.history_path, self.top_sites_path, self.shortcuts_path]:
            if db_file.exists():
                try:
                    conn = sqlite3.connect(str(db_file), timeout=1.5)
                    conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                    conn.close()
                    checkpointed += 1
                except Exception:
                    pass
        return checkpointed

    # --- BOOKMARKS ---
    def conceal_bookmarks(self, classifier) -> int:
        if not self.bookmarks_path.exists():
            return 0
        backup_path = self._create_backup(self.bookmarks_path)
        try:
            with open(self.bookmarks_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            concealed_count = 0
            roots = data.get("roots", {})
            for root_key, root_folder in roots.items():
                if isinstance(root_folder, dict):
                    concealed_count += self._process_folder_conceal(
                        classifier=classifier,
                        folder=root_folder,
                        parent_guid=root_folder.get("guid", root_key),
                        parent_name=root_folder.get("name", root_key)
                    )

            if concealed_count > 0:
                tmp_fd, tmp_path = tempfile.mkstemp(dir=self.profile_dir, prefix="bm_tmp_")
                with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                os.replace(tmp_path, self.bookmarks_path)

            return concealed_count
        except Exception as e:
            self._restore_backup(backup_path, self.bookmarks_path)
            return 0

    def _process_folder_conceal(self, classifier, folder: dict, parent_guid: str, parent_name: str) -> int:
        children = folder.get("children", [])
        new_children = []
        concealed_count = 0

        for idx, child in enumerate(children):
            c_type = child.get("type")
            if c_type == "url":
                url = child.get("url", "")
                name = child.get("name", "")
                res = classifier.classify_url(url, name)
                if res.is_sensitive:
                    self.vault.store_bookmark(
                        profile=f"{self.browser_name}:{self.profile_name}",
                        guid=child.get("guid", ""),
                        parent_guid=parent_guid,
                        parent_name=parent_name,
                        original_index=idx,
                        url=url,
                        title=name,
                        date_added=child.get("date_added", ""),
                        meta={"category": res.category, "reason": res.reason}
                    )
                    concealed_count += 1
                    continue
            elif c_type == "folder":
                concealed_count += self._process_folder_conceal(
                    classifier=classifier,
                    folder=child,
                    parent_guid=child.get("guid", ""),
                    parent_name=child.get("name", "")
                )
            new_children.append(child)

        folder["children"] = new_children
        return concealed_count

    def restore_bookmarks(self) -> int:
        if not self.bookmarks_path.exists():
            return 0

        stored_bms = self.vault.retrieve_bookmarks(profile=f"{self.browser_name}:{self.profile_name}")
        if not stored_bms:
            return 0

        backup_path = self._create_backup(self.bookmarks_path)
        try:
            with open(self.bookmarks_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            restored_count = 0
            roots = data.get("roots", {})

            for bm in stored_bms:
                parent_guid = bm.get("parent_guid")
                parent_name = bm.get("parent_name")
                target_folder = self._find_folder(roots, parent_guid, parent_name)
                if target_folder is None:
                    target_folder = roots.get("other", roots.get("bookmark_bar", {}))

                if "children" not in target_folder:
                    target_folder["children"] = []

                node = {
                    "type": "url",
                    "guid": bm.get("guid"),
                    "name": bm.get("title", ""),
                    "url": bm.get("url", ""),
                    "date_added": bm.get("date_added", "0")
                }
                idx = bm.get("original_index", len(target_folder["children"]))
                idx = min(max(0, idx), len(target_folder["children"]))
                target_folder["children"].insert(idx, node)
                restored_count += 1

            tmp_fd, tmp_path = tempfile.mkstemp(dir=self.profile_dir, prefix="bm_res_")
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_path, self.bookmarks_path)

            self.vault.clear_bookmarks(profile=f"{self.browser_name}:{self.profile_name}")
            return restored_count
        except Exception:
            self._restore_backup(backup_path, self.bookmarks_path)
            return 0

    def _find_folder(self, current: Any, target_guid: str, target_name: str) -> dict | None:
        if isinstance(current, dict):
            if current.get("guid") == target_guid or current.get("name") == target_name:
                if "children" in current:
                    return current
            for k, v in current.items():
                res = self._find_folder(v, target_guid, target_name)
                if res is not None:
                    return res
        elif isinstance(current, list):
            for item in current:
                res = self._find_folder(item, target_guid, target_name)
                if res is not None:
                    return res
        return None

    # --- HISTORY ---
    def conceal_history(self, classifier) -> int:
        if not self.history_path.exists():
            return 0
        if self.is_database_locked():
            return 0

        backup_path = self._create_backup(self.history_path)
        conn = None
        try:
            conn = sqlite3.connect(str(self.history_path), timeout=3.0)
            cur = conn.cursor()

            cur.execute("SELECT id, url, title, visit_count, typed_count, last_visit_time, hidden FROM urls")
            urls = cur.fetchall()

            sensitive_url_ids = []
            for row in urls:
                u_id, u_url, u_title, v_cnt, t_cnt, last_v, hid = row
                res = classifier.classify_url(u_url, u_title or "")
                if res.is_sensitive:
                    sensitive_url_ids.append((u_id, u_url, u_title, v_cnt, t_cnt, last_v, hid, res.category))

            if not sensitive_url_ids:
                conn.close()
                return 0

            id_list = [str(x[0]) for x in sensitive_url_ids]
            id_placeholders = ",".join("?" for _ in id_list)

            cur.execute(f"SELECT id, url, visit_time, from_visit, transition, segment_id, visit_duration FROM visits WHERE url IN ({id_placeholders})", id_list)
            visits = cur.fetchall()

            self.vault.store_history_batch(
                profile=f"{self.browser_name}:{self.profile_name}",
                urls=sensitive_url_ids,
                visits=visits
            )

            cur.execute("BEGIN TRANSACTION")
            cur.execute(f"DELETE FROM visits WHERE url IN ({id_placeholders})", id_list)
            cur.execute(f"DELETE FROM urls WHERE id IN ({id_placeholders})", id_list)
            conn.commit()
            conn.close()
            return len(sensitive_url_ids)
        except Exception:
            if conn:
                try: conn.close()
                except Exception: pass
            self._restore_backup(backup_path, self.history_path)
            return 0

    def restore_history(self) -> int:
        if not self.history_path.exists():
            return 0
        if self.is_database_locked():
            return 0

        stored = self.vault.retrieve_history(profile=f"{self.browser_name}:{self.profile_name}")
        if not stored.get("urls"):
            return 0

        backup_path = self._create_backup(self.history_path)
        conn = None
        try:
            conn = sqlite3.connect(str(self.history_path), timeout=3.0)
            cur = conn.cursor()
            cur.execute("BEGIN TRANSACTION")

            for u in stored["urls"]:
                cur.execute(
                    "INSERT OR REPLACE INTO urls (id, url, title, visit_count, typed_count, last_visit_time, hidden) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (u["id"], u["url"], u["title"], u["visit_count"], u["typed_count"], u["last_visit_time"], u["hidden"])
                )

            for v in stored.get("visits", []):
                cur.execute(
                    "INSERT OR REPLACE INTO visits (id, url, visit_time, from_visit, transition, segment_id, visit_duration) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (v["id"], v["url"], v["visit_time"], v["from_visit"], v["transition"], v["segment_id"], v["visit_duration"])
                )

            conn.commit()
            conn.close()

            self.vault.clear_history(profile=f"{self.browser_name}:{self.profile_name}")
            return len(stored["urls"])
        except Exception:
            if conn:
                try: conn.close()
                except Exception: pass
            self._restore_backup(backup_path, self.history_path)
            return 0

    # --- TOP SITES & SHORTCUTS ---
    def conceal_top_sites(self, classifier) -> int:
        if not self.top_sites_path.exists():
            return 0
        if self.is_database_locked():
            return 0

        backup_path = self._create_backup(self.top_sites_path)
        conn = None
        try:
            conn = sqlite3.connect(str(self.top_sites_path), timeout=3.0)
            cur = conn.cursor()
            cur.execute("SELECT url, url_rank, title FROM top_sites")
            rows = cur.fetchall()

            sensitive = []
            for r in rows:
                u, rank, t = r
                if classifier.classify_url(u, t or "").is_sensitive:
                    sensitive.append((u, rank, t))

            if sensitive:
                self.vault.store_top_sites(profile=f"{self.browser_name}:{self.profile_name}", items=sensitive)
                placeholders = ",".join("?" for _ in sensitive)
                cur.execute(f"DELETE FROM top_sites WHERE url IN ({placeholders})", [s[0] for s in sensitive])
                conn.commit()

            conn.close()
            return len(sensitive)
        except Exception:
            if conn:
                try: conn.close()
                except Exception: pass
            self._restore_backup(backup_path, self.top_sites_path)
            return 0

    def restore_top_sites(self) -> int:
        if not self.top_sites_path.exists():
            return 0
        if self.is_database_locked():
            return 0

        items = self.vault.retrieve_top_sites(profile=f"{self.browser_name}:{self.profile_name}")
        if not items:
            return 0

        backup_path = self._create_backup(self.top_sites_path)
        conn = None
        try:
            conn = sqlite3.connect(str(self.top_sites_path), timeout=3.0)
            cur = conn.cursor()
            for it in items:
                cur.execute("INSERT OR REPLACE INTO top_sites (url, url_rank, title) VALUES (?, ?, ?)", (it["url"], it["rank"], it["title"]))
            conn.commit()
            conn.close()
            self.vault.clear_top_sites(profile=f"{self.browser_name}:{self.profile_name}")
            return len(items)
        except Exception:
            if conn:
                try: conn.close()
                except Exception: pass
            self._restore_backup(backup_path, self.top_sites_path)
            return 0

    def shred_caches(self) -> int:
        if not self._offline_edit_permitted():
            return 0
        """Clear thumbnails, favicons and GPU caches when requested."""
        shredded = 0
        cache_targets = [
            self.profile_dir / "Thumbnails",
            self.profile_dir / "GPUCache",
            self.profile_dir / "Code Cache"
        ]
        for target in cache_targets:
            if target.is_file():
                try:
                    target.unlink()
                    shredded += 1
                except Exception:
                    pass
            elif target.is_dir():
                try:
                    shutil.rmtree(target, ignore_errors=True)
                    shredded += 1
                except Exception:
                    pass
        return shredded

    def conceal_all(self, classifier) -> dict:
        if not self._offline_edit_permitted():
            return {"bookmarks": 0, "history": 0, "top_sites": 0}
        self.checkpoint_sqlite_wal()
        bm = self.conceal_bookmarks(classifier)
        hist = self.conceal_history(classifier)
        ts = self.conceal_top_sites(classifier)
        return {"bookmarks": bm, "history": hist, "top_sites": ts}

    def restore_all(self) -> dict:
        if not self._offline_edit_permitted():
            return {"bookmarks": 0, "history": 0, "top_sites": 0}
        bm = self.restore_bookmarks()
        hist = self.restore_history()
        ts = self.restore_top_sites()
        return {"bookmarks": bm, "history": hist, "top_sites": ts}
