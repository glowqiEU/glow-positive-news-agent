import hashlib
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
    return conn


def fingerprint(title: str, urls: Iterable[str]) -> str:
    canonical = title.strip().lower() + "|" + "|".join(sorted(u.strip() for u in urls if u))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def has_seen(fp: str) -> bool:
    with _connect() as conn:
        row = conn.execute("SELECT 1 FROM stories WHERE fingerprint = ?", (fp,)).fetchone()
        return row is not None


def mark_seen(fp: str, title: str, primary_url: Optional[str]) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO stories (fingerprint, title, primary_url) VALUES (?, ?, ?)",
            (fp, title, primary_url),
        )
        conn.commit()
