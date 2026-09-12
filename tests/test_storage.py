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
            self.assertIn("delivery_status", columns)
            self.assertIn("delivery_error", columns)

    def test_delivery_reservation_is_atomic_and_completable(self):
        with TemporaryDirectory() as directory, patch.object(
            storage, "DB_PATH", Path(directory) / "stories.db"
        ):
            self.assertTrue(storage.reserve_delivery("fp", "Title", "https://primary.example/a", "event"))
            self.assertFalse(storage.reserve_delivery("fp", "Title", "https://primary.example/a", "event"))
            storage.complete_delivery("fp")
            with storage._connect() as conn:
                row = conn.execute("SELECT delivery_status FROM stories WHERE fingerprint = 'fp'").fetchone()
            self.assertEqual(row[0], "published")

    def test_uncertain_delivery_remains_deduplicated(self):
        with TemporaryDirectory() as directory, patch.object(
            storage, "DB_PATH", Path(directory) / "stories.db"
        ):
            storage.reserve_delivery("fp", "Title", "https://primary.example/a", "event")
            storage.record_delivery_uncertain("fp", "timeout after request")
            self.assertTrue(storage.has_seen("fp", "event", "https://primary.example/a"))
            with storage._connect() as conn:
                row = conn.execute("SELECT delivery_status, delivery_error FROM stories WHERE fingerprint = 'fp'").fetchone()
            self.assertEqual(row, ("uncertain", "timeout after request"))


if __name__ == "__main__":
    unittest.main()
