"""SQLite storage for encrypted tab and bookmark recovery records.

The schema also retains tables for older offline browser operations.
Those aren't part of the normal live-browser path.
"""

import sqlite3
import json
import base64
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from veil.crypto import VaultCrypto, KeyManager, encrypt_with_passphrase, decrypt_with_passphrase


class Vault:
    # Portable backups contain clear-text records only *inside* an authenticated,
    # passphrase-encrypted envelope. Never export machine-specific vault keys.
    BACKUP_MAGIC = b"VEILVAULT\n2\n"
    LEGACY_BACKUP_MAGIC = b"VEILVAULT\n1\n"
    BACKUP_FIELDS = {
        "vault_bookmarks": ("id", "profile", "guid", "parent_guid", "parent_name", "original_index", "url_enc", "title_enc", "date_added", "date_last_used", "meta_info_enc", "concealed_at", "restored"),
        "vault_tabs": ("token", "profile", "url_enc", "created_at"),
        "vault_history_urls": ("original_id", "profile", "url_enc", "title_enc", "visit_count", "typed_count", "last_visit_time", "hidden", "concealed_at", "restored"),
        "vault_history_visits": ("original_id", "profile", "url_id", "visit_time", "from_visit", "transition", "segment_id", "visit_duration", "concealed_at", "restored"),
        "vault_top_sites": ("id", "profile", "url_enc", "url_rank", "title_enc", "concealed_at", "restored"),
        "vault_firefox_places": ("id", "profile", "url_enc", "title_enc", "visit_count", "typed", "frecency", "last_visit_date", "guid", "category"),
        "vault_firefox_bookmarks": ("id", "profile", "type", "fk", "parent", "position", "title_enc", "dateAdded", "lastModified", "guid"),
        "vault_firefox_visits": ("id", "profile", "from_visit", "place_id", "visit_date", "visit_type", "session"),
    }
    ENCRYPTED_FIELDS = frozenset({"url_enc", "title_enc", "meta_info_enc"})
    DEFAULT_VAULT_PATH = Path.home() / ".config" / "veil" / "vault.db"

    def __init__(self, db_path: Path | None = None, crypto: VaultCrypto | None = None):
        self.db_path = Path(db_path) if db_path else self.DEFAULT_VAULT_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.crypto = crypto or VaultCrypto(KeyManager(self.db_path.parent))
        self._init_db()
        try:
            self.db_path.chmod(0o600)
        except OSError:
            pass

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=FULL;")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._get_connection() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS vault_state (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS vault_bookmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile TEXT NOT NULL,
                guid TEXT,
                parent_guid TEXT,
                parent_name TEXT,
                original_index INTEGER,
                url_enc TEXT NOT NULL,
                title_enc TEXT,
                date_added TEXT,
                date_last_used TEXT,
                meta_info_enc TEXT,
                concealed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                restored INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS vault_tabs (
                token TEXT NOT NULL,
                profile TEXT NOT NULL,
                url_enc TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (profile, token)
            );

            CREATE TABLE IF NOT EXISTS vault_history_urls (
                original_id INTEGER NOT NULL,
                profile TEXT NOT NULL,
                url_enc TEXT NOT NULL,
                title_enc TEXT,
                visit_count INTEGER,
                typed_count INTEGER,
                last_visit_time INTEGER,
                hidden INTEGER,
                concealed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                restored INTEGER DEFAULT 0,
                PRIMARY KEY (profile, original_id)
            );

            CREATE TABLE IF NOT EXISTS vault_history_visits (
                original_id INTEGER NOT NULL,
                profile TEXT NOT NULL,
                url_id INTEGER,
                visit_time INTEGER,
                from_visit INTEGER,
                transition INTEGER,
                segment_id INTEGER,
                visit_duration INTEGER,
                concealed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                restored INTEGER DEFAULT 0,
                PRIMARY KEY (profile, original_id)
            );

            CREATE TABLE IF NOT EXISTS vault_top_sites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile TEXT NOT NULL,
                url_enc TEXT NOT NULL,
                url_rank INTEGER,
                title_enc TEXT,
                concealed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                restored INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS vault_firefox_places (
                id INTEGER NOT NULL,
                profile TEXT NOT NULL,
                url_enc TEXT NOT NULL,
                title_enc TEXT,
                visit_count INTEGER,
                typed INTEGER,
                frecency INTEGER,
                last_visit_date INTEGER,
                guid TEXT,
                category TEXT,
                PRIMARY KEY (profile, id)
            );

            CREATE TABLE IF NOT EXISTS vault_firefox_bookmarks (
                id INTEGER NOT NULL,
                profile TEXT NOT NULL,
                type INTEGER,
                fk INTEGER,
                parent INTEGER,
                position INTEGER,
                title_enc TEXT,
                dateAdded INTEGER,
                lastModified INTEGER,
                guid TEXT,
                PRIMARY KEY (profile, id)
            );

            CREATE TABLE IF NOT EXISTS vault_firefox_visits (
                id INTEGER NOT NULL,
                profile TEXT NOT NULL,
                from_visit INTEGER,
                place_id INTEGER,
                visit_date INTEGER,
                visit_type INTEGER,
                session INTEGER,
                PRIMARY KEY (profile, id)
            );
            """)

    def get_state(self, key: str, default: Any = None) -> Any:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT value FROM vault_state WHERE key = ?", (key,))
            row = cur.fetchone()
            if not row:
                return default
            try:
                return json.loads(row["value"])
            except Exception:
                return row["value"]

    def set_state(self, key: str, value: Any):
        val_str = json.dumps(value) if not isinstance(value, str) else value
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO vault_state (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                (key, val_str)
            )

    # Keep original URLs in the vault, not in the paused tab's address bar.
    def store_tab(self, profile: str, token: str, url: str):
        with self._get_connection() as conn:
            conn.execute("INSERT OR IGNORE INTO vault_tabs(profile, token, url_enc) VALUES (?, ?, ?)",
                         (profile, token, self.crypto.encrypt_str(url)))

    def store_tabs(self, profile: str, tabs: list[tuple[str, str]]):
        """Durably encrypt a batch of tabs in one SQLite transaction.

        Acknowledgement is returned only after the entire transaction commits;
        a failed batch cannot cause the extension to navigate away.
        """
        encrypted = [(profile, token, self.crypto.encrypt_str(url)) for token, url in tabs]
        with self._get_connection() as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO vault_tabs(profile, token, url_enc) VALUES (?, ?, ?)",
                encrypted,
            )

    def retrieve_tabs(self, profile: str, tokens: list[str]) -> dict[str, str]:
        """Resolve several tab tokens using one connection. Much less chatter."""
        if not tokens:
            return {}
        marks = ",".join("?" for _ in tokens)
        with self._get_connection() as conn:
            rows = conn.execute(
                f"SELECT token, url_enc FROM vault_tabs WHERE profile=? AND token IN ({marks})",
                [profile, *tokens],
            ).fetchall()
        return {row["token"]: self.crypto.decrypt_str(row["url_enc"]) for row in rows}

    def clear_tabs(self, profile: str, tokens: list[str]) -> int:
        """Only drop restored tokens, and do it in one transation."""
        if not tokens:
            return 0
        marks = ",".join("?" for _ in tokens)
        with self._get_connection() as conn:
            cur = conn.execute(
                f"DELETE FROM vault_tabs WHERE profile=? AND token IN ({marks})",
                [profile, *tokens],
            )
            return cur.rowcount

    def retrieve_tab(self, profile: str, token: str) -> str | None:
        with self._get_connection() as conn:
            row = conn.execute("SELECT url_enc FROM vault_tabs WHERE profile=? AND token=?", (profile, token)).fetchone()
        return self.crypto.decrypt_str(row["url_enc"]) if row else None

    def clear_tab(self, profile: str, token: str) -> bool:
        with self._get_connection() as conn:
            cur = conn.execute("DELETE FROM vault_tabs WHERE profile=? AND token=?", (profile, token))
            return cur.rowcount > 0

    # Bookmarks
    def store_bookmark(self, profile: str, guid: str, parent_guid: str, parent_name: str,
                       original_index: int, url: str, title: str, date_added: str = "", meta: dict | None = None):
        url_enc = self.crypto.encrypt_str(url)
        title_enc = self.crypto.encrypt_str(title)
        meta_enc = self.crypto.encrypt_str(json.dumps(meta or {}))
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT INTO vault_bookmarks (profile, guid, parent_guid, parent_name, original_index, url_enc, title_enc, date_added, meta_info_enc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (profile, guid, parent_guid, parent_name, original_index, url_enc, title_enc, date_added, meta_enc))

    def store_live_bookmark(self, profile: str, guid: str, parent_guid: str,
                            original_index: int, url: str, title: str, date_added: str = ""):
        """Save encrypted bookmark data first. A sucess reply means it committed."""
        with self._get_connection() as conn:
            # Lock before SELECT, not after: multiple native connections can
            # otherwise stage the same bookmark twice concurrently.
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT id FROM vault_bookmarks WHERE profile=? AND guid=? AND restored=0 LIMIT 1",
                (profile, guid),
            ).fetchone()
            if row:
                return row["id"]
            cur = conn.execute("""
                INSERT INTO vault_bookmarks
                (profile, guid, parent_guid, parent_name, original_index,
                 url_enc, title_enc, date_added, meta_info_enc)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (profile, guid, parent_guid, "", original_index,
                  self.crypto.encrypt_str(url), self.crypto.encrypt_str(title),
                  date_added, self.crypto.encrypt_str("{}")))
            return cur.lastrowid

    def clear_bookmark_entry(self, profile: str, vault_id: int) -> bool:
        if not isinstance(vault_id, int) or vault_id <= 0:
            return False
        with self._get_connection() as conn:
            cur = conn.execute("DELETE FROM vault_bookmarks WHERE profile=? AND id=?", (profile, vault_id))
            return cur.rowcount == 1

    def retrieve_bookmarks(self, profile: str) -> list[dict]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM vault_bookmarks WHERE profile = ? AND restored = 0 ORDER BY id ASC", (profile,))
            rows = cur.fetchall()
            results = []
            for r in rows:
                results.append({
                    "id": r["id"],
                    "guid": r["guid"],
                    "parent_guid": r["parent_guid"],
                    "parent_name": r["parent_name"],
                    "original_index": r["original_index"],
                    "url": self.crypto.decrypt_str(r["url_enc"]),
                    "title": self.crypto.decrypt_str(r["title_enc"]),
                    "date_added": r["date_added"],
                    "meta": json.loads(self.crypto.decrypt_str(r["meta_info_enc"]) or "{}")
                })
            return results

    def clear_bookmarks(self, profile: str):
        with self._get_connection() as conn:
            conn.execute("DELETE FROM vault_bookmarks WHERE profile = ?", (profile,))

    # History
    def store_history_batch(self, profile: str, urls: list, visits: list):
        with self._get_connection() as conn:
            cur = conn.cursor()
            for u in urls:
                u_id, u_url, u_title, v_cnt, t_cnt, last_v, hid, cat = u
                cur.execute("""
                INSERT OR REPLACE INTO vault_history_urls (original_id, profile, url_enc, title_enc, visit_count, typed_count, last_visit_time, hidden)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (u_id, profile, self.crypto.encrypt_str(u_url), self.crypto.encrypt_str(u_title or ""), v_cnt, t_cnt, last_v, hid))

            for v in visits:
                v_id, v_url_id, v_time, from_v, trans, seg_id, dur = v
                cur.execute("""
                INSERT OR REPLACE INTO vault_history_visits (original_id, profile, url_id, visit_time, from_visit, transition, segment_id, visit_duration)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (v_id, profile, v_url_id, v_time, from_v, trans, seg_id, dur))

    def retrieve_history(self, profile: str) -> dict:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM vault_history_urls WHERE profile = ?", (profile,))
            url_rows = cur.fetchall()
            urls = []
            for r in url_rows:
                urls.append({
                    "id": r["original_id"],
                    "url": self.crypto.decrypt_str(r["url_enc"]),
                    "title": self.crypto.decrypt_str(r["title_enc"]),
                    "visit_count": r["visit_count"],
                    "typed_count": r["typed_count"],
                    "last_visit_time": r["last_visit_time"],
                    "hidden": r["hidden"]
                })

            cur.execute("SELECT * FROM vault_history_visits WHERE profile = ?", (profile,))
            visit_rows = cur.fetchall()
            visits = []
            for r in visit_rows:
                visits.append({
                    "id": r["original_id"],
                    "url": r["url_id"],
                    "visit_time": r["visit_time"],
                    "from_visit": r["from_visit"],
                    "transition": r["transition"],
                    "segment_id": r["segment_id"],
                    "visit_duration": r["visit_duration"]
                })

            return {"urls": urls, "visits": visits}

    def clear_history(self, profile: str):
        with self._get_connection() as conn:
            conn.execute("DELETE FROM vault_history_urls WHERE profile = ?", (profile,))
            conn.execute("DELETE FROM vault_history_visits WHERE profile = ?", (profile,))

    # Top Sites
    def store_top_sites(self, profile: str, items: list):
        with self._get_connection() as conn:
            cur = conn.cursor()
            for it in items:
                u, rank, t = it
                cur.execute("""
                INSERT INTO vault_top_sites (profile, url_enc, url_rank, title_enc)
                VALUES (?, ?, ?, ?)
                """, (profile, self.crypto.encrypt_str(u), rank, self.crypto.encrypt_str(t or "")))

    def retrieve_top_sites(self, profile: str) -> list[dict]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM vault_top_sites WHERE profile = ?", (profile,))
            rows = cur.fetchall()
            return [{
                "url": self.crypto.decrypt_str(r["url_enc"]),
                "rank": r["url_rank"],
                "title": self.crypto.decrypt_str(r["title_enc"])
            } for r in rows]

    def clear_top_sites(self, profile: str):
        with self._get_connection() as conn:
            conn.execute("DELETE FROM vault_top_sites WHERE profile = ?", (profile,))

    # Firefox Places
    def store_firefox_places(self, profile: str, places: list, bookmarks: list, visits: list):
        with self._get_connection() as conn:
            cur = conn.cursor()
            for p in places:
                p_id, u_url, u_title, v_cnt, typed, frec, last_v, guid, cat = p
                cur.execute("""
                INSERT OR REPLACE INTO vault_firefox_places (id, profile, url_enc, title_enc, visit_count, typed, frecency, last_visit_date, guid, category)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (p_id, profile, self.crypto.encrypt_str(u_url), self.crypto.encrypt_str(u_title or ""), v_cnt, typed, frec, last_v, guid, cat))

            for b in bookmarks:
                b_id, b_type, fk, parent, pos, t, d_add, d_mod, guid = b
                cur.execute("""
                INSERT OR REPLACE INTO vault_firefox_bookmarks (id, profile, type, fk, parent, position, title_enc, dateAdded, lastModified, guid)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (b_id, profile, b_type, fk, parent, pos, self.crypto.encrypt_str(t or ""), d_add, d_mod, guid))

            for v in visits:
                v_id, f_v, place_id, v_date, v_type, sess = v
                cur.execute("""
                INSERT OR REPLACE INTO vault_firefox_visits (id, profile, from_visit, place_id, visit_date, visit_type, session)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (v_id, profile, f_v, place_id, v_date, v_type, sess))

    def retrieve_firefox_places(self, profile: str) -> dict:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM vault_firefox_places WHERE profile = ?", (profile,))
            p_rows = cur.fetchall()
            places = [{
                "id": r["id"],
                "url": self.crypto.decrypt_str(r["url_enc"]),
                "title": self.crypto.decrypt_str(r["title_enc"]),
                "visit_count": r["visit_count"],
                "typed": r["typed"],
                "frecency": r["frecency"],
                "last_visit_date": r["last_visit_date"],
                "guid": r["guid"]
            } for r in p_rows]

            cur.execute("SELECT * FROM vault_firefox_bookmarks WHERE profile = ?", (profile,))
            b_rows = cur.fetchall()
            bookmarks = [{
                "id": r["id"],
                "type": r["type"],
                "fk": r["fk"],
                "parent": r["parent"],
                "position": r["position"],
                "title": self.crypto.decrypt_str(r["title_enc"]),
                "dateAdded": r["dateAdded"],
                "lastModified": r["lastModified"],
                "guid": r["guid"]
            } for r in b_rows]

            cur.execute("SELECT * FROM vault_firefox_visits WHERE profile = ?", (profile,))
            v_rows = cur.fetchall()
            visits = [{
                "id": r["id"],
                "from_visit": r["from_visit"],
                "place_id": r["place_id"],
                "visit_date": r["visit_date"],
                "visit_type": r["visit_type"],
                "session": r["session"]
            } for r in v_rows]

            return {"places": places, "bookmarks": bookmarks, "visits": visits}

    def clear_firefox_places(self, profile: str):
        with self._get_connection() as conn:
            conn.execute("DELETE FROM vault_firefox_places WHERE profile = ?", (profile,))
            conn.execute("DELETE FROM vault_firefox_bookmarks WHERE profile = ?", (profile,))
            conn.execute("DELETE FROM vault_firefox_visits WHERE profile = ?", (profile,))

    def count_concealed_items(self) -> dict:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT count(*) FROM vault_tabs")
            tab_count = cur.fetchone()[0]

            cur.execute("SELECT count(*) FROM vault_bookmarks WHERE restored = 0")
            bm_count = cur.fetchone()[0]

            cur.execute("SELECT count(*) FROM vault_history_urls WHERE restored = 0")
            hist_count = cur.fetchone()[0]

            cur.execute("SELECT count(*) FROM vault_top_sites WHERE restored = 0")
            ts_count = cur.fetchone()[0]

            cur.execute("SELECT count(*) FROM vault_firefox_bookmarks")
            ff_bm_count = cur.fetchone()[0]

            cur.execute("SELECT count(*) FROM vault_firefox_places")
            ff_places_count = cur.fetchone()[0]

            return {
                "bookmarks": bm_count + ff_bm_count,
                "history_urls": hist_count + ff_places_count,
                "top_sites": ts_count,
                "tabs": tab_count,
                "history_visits": self._count_table(conn, "vault_history_visits") + self._count_table(conn, "vault_firefox_visits"),
                "search_terms": 0,
            }

    @staticmethod
    def _count_table(conn, table: str) -> int:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def _decrypt_backup_field(self, value):
        """If a field wont decrypt, fail export. Empty data isn't a backup."""
        if value is None or value == "":
            return value
        raw = base64.b64decode(value.encode("ascii"), altchars=b"-_", validate=True)
        if len(raw) < 28:
            raise ValueError("Corrupt vault ciphertext; export aborted")
        return self.crypto.aesgcm.decrypt(raw[:12], raw[12:], None).decode("utf-8")

    def export_vault(self, destination: Path, passphrase: str) -> dict:
        """Create a portable, all-table encrypted backup without plaintext temp files."""
        from veil.crypto import MIN_BACKUP_PASSPHRASE_LENGTH
        if not isinstance(passphrase, str) or len(passphrase.strip()) < MIN_BACKUP_PASSPHRASE_LENGTH:
            raise ValueError("Use a backup passphrase of at least 16 characters")
        destination = Path(destination).expanduser()
        with self._get_connection() as conn:
            conn.execute("BEGIN")  # consistent WAL snapshot, including in-flight updates
            tables = {}
            for name, fields in self.BACKUP_FIELDS.items():
                rows = conn.execute(f"SELECT {', '.join(fields)} FROM {name}").fetchall()
                tables[name] = [
                    {field: (self._decrypt_backup_field(row[field]) if field in self.ENCRYPTED_FIELDS else row[field])
                     for field in fields}
                    for row in rows
                ]
            conn.rollback()

        payload = json.dumps({"format": "veil-portable-vault", "version": 1, "tables": tables},
                             separators=(",", ":"), ensure_ascii=False)
        content = self.BACKUP_MAGIC + encrypt_with_passphrase(payload, passphrase).encode("ascii") + b"\n"
        # Backup filenames are one-shot on purpose. Dont overwrite an old one.
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
        return {name: len(rows) for name, rows in tables.items()}

    def import_vault(self, source: Path, passphrase: str) -> dict:
        """Merge a portable backup atomically; reject conflicts without losing live data."""
        if not passphrase:
            raise ValueError("A backup passphrase is required")
        source = Path(source).expanduser()
        raw = source.read_bytes()
        if raw.startswith(self.BACKUP_MAGIC):
            prefix, legacy = self.BACKUP_MAGIC, False
        elif raw.startswith(self.LEGACY_BACKUP_MAGIC):
            prefix, legacy = self.LEGACY_BACKUP_MAGIC, True
        else:
            raise ValueError("Unsupported or damaged Veil backup")
        try:
            payload = json.loads(decrypt_with_passphrase(
                raw[len(prefix):].strip().decode("ascii"), passphrase, legacy=legacy
            ))
        except Exception as exc:
            raise ValueError("Backup decryption failed (wrong passphrase or damaged file)") from exc
        if (not isinstance(payload, dict) or payload.get("format") != "veil-portable-vault"
                or payload.get("version") != 1 or not isinstance(payload.get("tables"), dict)
                or set(payload["tables"]) != set(self.BACKUP_FIELDS)):
            raise ValueError("Unrecognized Veil vault backup format")

        prepared = {}
        for name, fields in self.BACKUP_FIELDS.items():
            rows = payload["tables"][name]
            if not isinstance(rows, list):
                raise ValueError(f"Malformed backup table: {name}")
            prepared[name] = []
            for row in rows:
                if not isinstance(row, dict) or set(row) != set(fields):
                    raise ValueError(f"Malformed backup record: {name}")
                record = []
                for field in fields:
                    value = row[field]
                    if not (value is None or isinstance(value, (str, int, float)) and not isinstance(value, bool)):
                        raise ValueError(f"Invalid backup field {name}.{field}")
                    if field in self.ENCRYPTED_FIELDS:
                        if value is not None and not isinstance(value, str):
                            raise ValueError(f"Invalid encrypted backup field {name}.{field}")
                        value = self.crypto.encrypt_str(value) if value is not None else None
                    record.append(value)
                prepared[name].append(tuple(record))

        with self._get_connection() as conn:
            # INSERT only. A collision shoud roll back the whole import, not replace anything.
            for name, fields in self.BACKUP_FIELDS.items():
                placeholders = ", ".join("?" for _ in fields)
                conn.executemany(f"INSERT INTO {name} ({', '.join(fields)}) VALUES ({placeholders})", prepared[name])
        return {name: len(rows) for name, rows in prepared.items()}
