import io
import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import main
import storage


def salmon_story():
    return {
        "title_lt": "Lašišos sugrįžo į San Geronimo upelį",
        "summary_lt": "Stebėsena patvirtino reikšmingą lašišų sugrįžimą po atkūrimo darbų.",
        "topic": "wildlife",
        "evidence_level": "measured_real_world",
        "impact_status": "measured_outcome",
        "positive_progress": "recovery_or_restoration",
        "progress_significance": "meaningful",
        "real_world_significance": 8,
        "freshness": 9,
        "credibility": 9,
        "positive_impact": 8,
        "interestingness": 7,
        "specific_evidence": 9,
        "total_score": 42,
        "development_at": datetime.now(timezone.utc).isoformat(),
        "source_urls": ["https://agency.example/san-geronimo-salmon"],
        "primary_source": "https://agency.example/san-geronimo-salmon",
        "primary_source_type": "responsible_organization",
        "primary_evidence": "Monitoring confirms the salmon return.",
        "event_key": "san-geronimo-salmon-return-2026-09-12",
        "verification_status": "verified",
        "verification_notes": "Primary monitoring result and date checked.",
    }


class DryRunWorkflowTests(unittest.TestCase):
    def test_consecutive_dry_runs_deduplicate_without_affecting_live_state(self):
        with TemporaryDirectory() as directory:
            production_db = Path(directory) / "production.db"
            preview_db = Path(directory) / "preview.db"
            env = {
                "DRY_RUN": "true",
                "PUBLISH_APPROVED": "false",
                "DRY_RUN_DB_PATH": str(preview_db),
            }
            output = io.StringIO()
            with patch.object(storage, "DB_PATH", production_db), patch.dict(
                os.environ, env, clear=False
            ), patch.object(main, "find_positive_news", return_value=[salmon_story()]), patch.object(
                main, "send_telegram_message"
            ) as send, patch("sys.stdout", output):
                main.run()
                main.run()

            rendered = output.getvalue()
            self.assertEqual(rendered.count("--- CANDIDATE ---"), 1)
            self.assertIn("Skipped duplicate dry-run preview", rendered)
            self.assertIn("Real-world significance: 8/10", rendered)
            send.assert_not_called()
            with storage._connect(production_db) as conn:
                production_count = conn.execute("SELECT COUNT(*) FROM stories").fetchone()[0]
            self.assertEqual(production_count, 0)


if __name__ == "__main__":
    unittest.main()
