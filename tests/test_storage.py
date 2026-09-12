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

    def test_database_path_environment_selects_persistent_location(self):
        with TemporaryDirectory() as directory:
            configured = Path(directory) / "volume" / "stories.db"
            configured.parent.mkdir()
            with patch.dict("os.environ", {"DATABASE_PATH": str(configured)}, clear=False):
                self.assertEqual(storage.production_db_path(), configured)
                with storage._connect() as conn:
                    journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
                self.assertTrue(configured.exists())
                self.assertEqual(journal_mode, "wal")

    def test_uncertain_delivery_requires_explicit_resolution(self):
        with TemporaryDirectory() as directory, patch.object(
            storage, "DB_PATH", Path(directory) / "stories.db"
        ), patch.dict("os.environ", {}, clear=True):
            storage.reserve_delivery("fp", "Title", "https://primary.example/a", "event")
            storage.record_delivery_uncertain("fp", "timeout")
            self.assertEqual(len(storage.list_uncertain_deliveries()), 1)
            self.assertTrue(storage.resolve_uncertain_delivery("fp", "published"))
            self.assertEqual(storage.list_uncertain_deliveries(), [])
            self.assertTrue(storage.has_seen("fp", "event", "https://primary.example/a"))

    def test_retry_resolution_releases_only_uncertain_row(self):
        with TemporaryDirectory() as directory, patch.object(
            storage, "DB_PATH", Path(directory) / "stories.db"
        ), patch.dict("os.environ", {}, clear=True):
            storage.reserve_delivery("fp", "Title", "https://primary.example/a", "event")
            storage.record_delivery_uncertain("fp", "timeout")
            self.assertTrue(storage.resolve_uncertain_delivery("fp", "retry"))
            self.assertFalse(storage.has_seen("fp", "event", "https://primary.example/a"))

    def test_storage_validation_rejects_shared_database_file(self):
        with TemporaryDirectory() as directory:
            shared = str(Path(directory) / "shared.db")
            with patch.dict("os.environ", {
                "DATABASE_PATH": shared,
                "DRY_RUN_DB_PATH": shared,
            }, clear=True):
                with self.assertRaisesRegex(RuntimeError, "must be different"):
                    storage.validate_storage_configuration()

    def test_railway_storage_requires_absolute_paths(self):
        with patch.dict("os.environ", {
            "DATABASE_PATH": "positive_news.db",
            "DRY_RUN_DB_PATH": "positive_news_dry_run.db",
            "RAILWAY_ENVIRONMENT_ID": "environment-id",
        }, clear=True):
            with self.assertRaisesRegex(RuntimeError, "requires absolute"):
                storage.validate_storage_configuration()

    def test_railway_storage_accepts_distinct_writable_absolute_paths(self):
        with TemporaryDirectory() as directory:
            with patch.dict("os.environ", {
                "DATABASE_PATH": str(Path(directory) / "production.db"),
                "DRY_RUN_DB_PATH": str(Path(directory) / "preview.db"),
                "RAILWAY_ENVIRONMENT_NAME": "production",
            }, clear=True):
                storage.validate_storage_configuration()

    def test_preview_ledger_deduplicates_dry_runs_without_touching_delivery_db(self):
        with TemporaryDirectory() as directory:
            production_db = Path(directory) / "production.db"
            preview_db = Path(directory) / "preview.db"
            with patch.object(storage, "DB_PATH", production_db), patch.dict(
                "os.environ", {"DRY_RUN_DB_PATH": str(preview_db)}, clear=False
            ):
                storage.mark_previewed(
                    "preview-fp", "San Geronimo salmon", "https://agency.example/salmon",
                    "san-geronimo-salmon-return-2026-09-11",
                )
                self.assertTrue(storage.has_been_previewed(
                    "rewritten-fp", "san-geronimo-salmon-return-2026-09-11",
                    "https://other.example/salmon",
                ))
                self.assertFalse(storage.has_seen(
                    "preview-fp", "san-geronimo-salmon-return-2026-09-11",
                    "https://agency.example/salmon",
                ))
                with storage._connect(production_db) as conn:
                    count = conn.execute("SELECT COUNT(*) FROM stories").fetchone()[0]
                self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
