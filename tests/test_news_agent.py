import unittest
from unittest.mock import MagicMock, patch

from news_agent import _extract_json, _merge_verification, find_positive_news


class ResearchVerificationTests(unittest.TestCase):
    def test_extract_json_rejects_non_object_rows(self):
        with self.assertRaises(ValueError):
            _extract_json('[{"ok": true}, 4]')

    def test_merge_keeps_only_candidates_with_all_checks(self):
        candidates = [{"title_lt": "A", "summary_lt": "old"}, {"title_lt": "B"}]
        audits = [
            {"candidate_index": 0, "verified": True, "primary_source_verified": True,
             "claim_supported": True, "freshness_verified": True, "significance_verified": True,
             "progress_significance": "meaningful",
             "verification_notes": "checked", "corrected_summary_lt": "narrowed"},
            {"candidate_index": 1, "verified": True, "primary_source_verified": True,
             "claim_supported": False, "freshness_verified": True, "significance_verified": True,
             "progress_significance": "meaningful"},
        ]
        result = _merge_verification(candidates, audits)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["summary_lt"], "narrowed")
        self.assertEqual(result[0]["verification_status"], "verified")

    def test_duplicate_audit_index_fails_closed(self):
        candidates = [{"title_lt": "A"}]
        passing = {"candidate_index": 0, "verified": True, "primary_source_verified": True,
                   "claim_supported": True, "freshness_verified": True,
                   "significance_verified": True, "progress_significance": "meaningful"}
        self.assertEqual(_merge_verification(candidates, [passing, passing]), [])

    def test_missing_audit_fails_closed(self):
        self.assertEqual(_merge_verification([{"title_lt": "A"}], []), [])

    def test_temporary_red_tide_absence_fails_verification(self):
        candidates = [{"title_lt": "Red tide not detected this week"}]
        audits = [{
            "candidate_index": 0,
            "verified": True,
            "primary_source_verified": True,
            "claim_supported": True,
            "freshness_verified": True,
            "significance_verified": False,
            "progress_significance": "temporary_or_routine",
            "verification_notes": "Routine weekly non-detection only.",
        }]
        self.assertEqual(_merge_verification(candidates, audits), [])

    @patch("news_agent.OpenAI")
    def test_openai_client_uses_bounded_timeout_and_retries(self, openai):
        client = MagicMock()
        client.responses.create.return_value.output_text = "[]"
        openai.return_value = client
        env = {
            "OPENAI_API_KEY": "test-key",
            "OPENAI_TIMEOUT_SECONDS": "45",
            "OPENAI_MAX_RETRIES": "3",
        }
        with patch.dict("os.environ", env, clear=False):
            self.assertEqual(find_positive_news(), [])
        openai.assert_called_once_with(api_key="test-key", timeout=45.0, max_retries=3)


if __name__ == "__main__":
    unittest.main()
