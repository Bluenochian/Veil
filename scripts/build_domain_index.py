#!/usr/bin/env python3
"""Build Veil's bundled domain index from a pinned, MIT-licensed upstream list.

Runs during source packaging, not during normal Veil operation.
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import tempfile
import urllib.request
from pathlib import Path

SOURCE_REVISION = "ee3bdbaddf49c756cf3340bb2e6a9dee5282d1c6"
SOURCE_URL = f"https://raw.githubusercontent.com/blocklistproject/Lists/{SOURCE_REVISION}/porn.txt"
EXPECTED_ENTRIES = 953_393
DOMAIN_RE = re.compile(r"(?=.{1,253}$)[a-z0-9_-]+(?:\.[a-z0-9_-]+)+\Z")
BATCH_SIZE = 10_000


def _parse_domains(lines):
    license_seen = False
    batch = []
    count = 0
    for raw in lines:
        line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        line = line.strip()
        if line.startswith("#"):
            if line == "# License: MIT":
                license_seen = True
            continue
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2 or parts[0] != "0.0.0.0":
            raise ValueError(f"Unexpected hosts-file entry at row {count + 1}")
        domain = parts[1].lower()
        if not DOMAIN_RE.fullmatch(domain):
            raise ValueError(f"Invalid domain at row {count + 1}")
        batch.append((domain,))
        count += 1
        if len(batch) >= BATCH_SIZE:
            yield batch
            batch = []
    if not license_seen:
        raise ValueError("Expected upstream MIT license notice is missing")
    if batch:
        yield batch


def build_index(source, output: Path, expected_count: int = EXPECTED_ENTRIES) -> int:
    """Build atomically: failed verification cannot replace an existing index."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=".veil-index-", suffix=".db", dir=output.parent, delete=False
    ) as tmp:
        temp_path = Path(tmp.name)
    try:
        with sqlite3.connect(temp_path) as conn:
            conn.execute("PRAGMA journal_mode=OFF")
            conn.execute("PRAGMA synchronous=OFF")
            conn.execute("CREATE TABLE domains (domain TEXT PRIMARY KEY) WITHOUT ROWID")
            for batch in _parse_domains(source):
                conn.executemany("INSERT INTO domains(domain) VALUES (?)", batch)
            actual = conn.execute("SELECT COUNT(*) FROM domains").fetchone()[0]
            if actual != expected_count:
                raise ValueError(
                    f"Domain index count mismatch: {actual} != {expected_count}"
                )
            conn.commit()
            result = conn.execute("PRAGMA integrity_check").fetchone()[0]
            if result != "ok":
                raise ValueError(f"SQLite integrity check failed: {result}")
        temp_path.replace(output)
        return actual
    finally:
        temp_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="Local upstream hosts file")
    parser.add_argument(
        "--output", type=Path,
        default=Path(__file__).resolve().parents[1] / "veil/data/adult_domains.db",
    )
    parser.add_argument("--expected-count", type=int, default=EXPECTED_ENTRIES)
    args = parser.parse_args()
    if args.source:
        with args.source.open("r", encoding="utf-8") as source:
            count = build_index(source, args.output, args.expected_count)
    else:
        request = urllib.request.Request(
            SOURCE_URL, headers={"User-Agent": "Veil-Index-Builder/1.0"}
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            count = build_index(response, args.output, args.expected_count)
    print(f"Bundled offline domain index: {count:,} entries at {args.output}")


if __name__ == "__main__":
    main()
