import hashlib
import re
import sqlite3
from pathlib import Path
from typing import Iterable, Optional

DB_PATH = Path("positive_news.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS stories (
            fingerprint TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            primary_url TEXT,
            posted_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    columns = {row[1] for row in conn.execute("PRAGMA table_info(stories)")}
    if "event_key" not in columns:
        conn.execute("ALTER TABLE stories ADD COLUMN event_key TEXT")
    if "canonical_primary_url" not in columns:
        conn.execute("ALTER TABLE stories ADD COLUMN canonical_primary_url TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_stories_event_key ON stories(event_key)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_stories_primary_url ON stories(canonical_primary_url)"
    )
    return conn


def fingerprint(title: str, urls: Iterable[str]) -> str:
    canonical = normalize_event_key(title) + "|" + "|".join(sorted(u.strip() for u in urls if u))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def normalize_event_key(value: str) -> str:
    """Normalize a model-supplied event identity into a stable comparison key."""
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")


def has_seen(fp: str, event_key: str = "", primary_url: str = "") -> bool:
    with _connect() as conn:
        normalized_key = normalize_event_key(event_key)
        row = conn.execute(
            """
            SELECT 1 FROM stories
            WHERE fingerprint = ?
               OR (? != '' AND event_key = ?)
               OR (? != '' AND (canonical_primary_url = ? OR primary_url = ?))
            LIMIT 1
            """,
            (fp, normalized_key, normalized_key, primary_url, primary_url, primary_url),
        ).fetchone()
        return row is not None


def mark_seen(fp: str, title: str, primary_url: Optional[str], event_key: str = "") -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO stories
                (fingerprint, title, primary_url, event_key, canonical_primary_url)
            VALUES (?, ?, ?, ?, ?)
            """,
            (fp, title, primary_url, normalize_event_key(event_key), primary_url),
        )
        conn.commit()
