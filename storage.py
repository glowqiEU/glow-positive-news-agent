import hashlib
import os
import re
import sqlite3
from pathlib import Path
from typing import Iterable, Optional

DB_PATH = Path("positive_news.db")


def production_db_path() -> Path:
    return Path(os.getenv("DATABASE_PATH", str(DB_PATH)))


def _connect(db_path: Optional[Path] = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or production_db_path(), timeout=30)
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
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
    if "delivery_status" not in columns:
        conn.execute("ALTER TABLE stories ADD COLUMN delivery_status TEXT NOT NULL DEFAULT 'published'")
    if "delivery_error" not in columns:
        conn.execute("ALTER TABLE stories ADD COLUMN delivery_error TEXT")
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


def has_seen(fp: str, event_key: str = "", primary_url: str = "",
             db_path: Optional[Path] = None) -> bool:
    with _connect(db_path) as conn:
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


def dry_run_db_path() -> Path:
    return Path(os.getenv("DRY_RUN_DB_PATH", "positive_news_dry_run.db"))


def validate_storage_configuration() -> None:
    production = production_db_path()
    preview = dry_run_db_path()
    if production.resolve() == preview.resolve():
        raise RuntimeError("DATABASE_PATH and DRY_RUN_DB_PATH must be different files")
    on_railway = bool(
        os.getenv("RAILWAY_ENVIRONMENT_ID") or os.getenv("RAILWAY_ENVIRONMENT_NAME")
    )
    if on_railway and (not production.is_absolute() or not preview.is_absolute()):
        raise RuntimeError("Railway requires absolute database paths on a persistent volume")
    for path in (production, preview):
        parent = path.parent
        if not parent.exists() or not parent.is_dir() or not os.access(str(parent), os.W_OK):
            raise RuntimeError(f"Database directory is not writable: {parent}")


def has_been_previewed(fp: str, event_key: str = "", primary_url: str = "") -> bool:
    return has_seen(fp, event_key, primary_url, dry_run_db_path())


def mark_previewed(fp: str, title: str, primary_url: Optional[str], event_key: str = "") -> None:
    """Record a dry-run preview separately; this must never affect live delivery state."""
    with _connect(dry_run_db_path()) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO stories
                (fingerprint, title, primary_url, event_key, canonical_primary_url, delivery_status)
            VALUES (?, ?, ?, ?, ?, 'previewed')
            """,
            (fp, title, primary_url, normalize_event_key(event_key), primary_url),
        )
        conn.commit()


def mark_seen(fp: str, title: str, primary_url: Optional[str], event_key: str = "") -> None:
    """Compatibility helper for importing an already-published story."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO stories
                (fingerprint, title, primary_url, event_key, canonical_primary_url, delivery_status)
            VALUES (?, ?, ?, ?, ?, 'published')
            """,
            (fp, title, primary_url, normalize_event_key(event_key), primary_url),
        )
        conn.commit()


def reserve_delivery(fp: str, title: str, primary_url: Optional[str], event_key: str = "") -> bool:
    """Atomically reserve a story before sending; false means it already exists."""
    with _connect() as conn:
        normalized_key = normalize_event_key(event_key)
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            """
            SELECT 1 FROM stories
            WHERE fingerprint = ?
               OR (? != '' AND event_key = ?)
               OR (? != '' AND (canonical_primary_url = ? OR primary_url = ?))
            LIMIT 1
            """,
            (fp, normalized_key, normalized_key, primary_url, primary_url, primary_url),
        ).fetchone()
        if existing:
            conn.rollback()
            return False
        conn.execute(
            """
            INSERT INTO stories
                (fingerprint, title, primary_url, event_key, canonical_primary_url, delivery_status)
            VALUES (?, ?, ?, ?, ?, 'pending')
            """,
            (fp, title, primary_url, normalized_key, primary_url),
        )
        conn.commit()
        return True


def complete_delivery(fp: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE stories SET delivery_status = 'published', delivery_error = NULL WHERE fingerprint = ?",
            (fp,),
        )
        conn.commit()


def record_delivery_uncertain(fp: str, error: str) -> None:
    """Retain the reservation because Telegram may have accepted a timed-out request."""
    with _connect() as conn:
        conn.execute(
            "UPDATE stories SET delivery_status = 'uncertain', delivery_error = ? WHERE fingerprint = ?",
            (error[:500], fp),
        )
        conn.commit()


def list_uncertain_deliveries() -> list[dict[str, str]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT fingerprint, title, COALESCE(primary_url, ''),
                   COALESCE(posted_at, ''), COALESCE(delivery_error, '')
            FROM stories
            WHERE delivery_status = 'uncertain'
            ORDER BY posted_at
            """
        ).fetchall()
    return [
        {"fingerprint": row[0], "title": row[1], "primary_url": row[2],
         "posted_at": row[3], "delivery_error": row[4]}
        for row in rows
    ]


def resolve_uncertain_delivery(fp: str, resolution: str) -> bool:
    """Resolve a manually checked uncertain send as published or safe to retry."""
    if resolution not in {"published", "retry"}:
        raise ValueError("resolution must be 'published' or 'retry'")
    with _connect() as conn:
        if resolution == "published":
            cursor = conn.execute(
                """
                UPDATE stories SET delivery_status = 'published', delivery_error = NULL
                WHERE fingerprint = ? AND delivery_status = 'uncertain'
                """,
                (fp,),
            )
        else:
            cursor = conn.execute(
                "DELETE FROM stories WHERE fingerprint = ? AND delivery_status = 'uncertain'",
                (fp,),
            )
        conn.commit()
        return cursor.rowcount == 1
