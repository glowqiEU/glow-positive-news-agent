from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import storage


class StorageDeduplicationTests(unittest.TestCase):
    def test_matches_event_key_across_changed_title_and_url(self):
        with TemporaryDirectory() as directory, patch.object(
            storage, "DB_PATH", Path(directory) / "stories.db"
        ):
            first = storage.fingerprint("First title", ["https://primary.example/a"])
            storage.mark_seen(first, "First title", "https://primary.example/a", "entity-result-2026-09-11")
            second = storage.fingerprint("Completely rewritten", ["https://news.example/b"])
            self.assertTrue(storage.has_seen(second, "entity-result-2026-09-11", "https://news.example/b"))

    def test_matches_same_primary_url_across_changed_event_key(self):
        with TemporaryDirectory() as directory, patch.object(
            storage, "DB_PATH", Path(directory) / "stories.db"
        ):
            first = storage.fingerprint("First", ["https://primary.example/a"])
            storage.mark_seen(first, "First", "https://primary.example/a", "first-key")
            second = storage.fingerprint("Second", ["https://primary.example/a"])
            self.assertTrue(storage.has_seen(second, "different-key", "https://primary.example/a"))

    def test_migrates_legacy_database(self):
        with TemporaryDirectory() as directory, patch.object(
            storage, "DB_PATH", Path(directory) / "stories.db"
        ):
            import sqlite3
            with sqlite3.connect(storage.DB_PATH) as conn:
                conn.execute("CREATE TABLE stories (fingerprint TEXT PRIMARY KEY, title TEXT NOT NULL, primary_url TEXT, posted_at TEXT DEFAULT CURRENT_TIMESTAMP)")
            with storage._connect() as conn:
                columns = {row[1] for row in conn.execute("PRAGMA table_info(stories)")}
            self.assertIn("event_key", columns)
            self.assertIn("canonical_primary_url", columns)


if __name__ == "__main__":
    unittest.main()
