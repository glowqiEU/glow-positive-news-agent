import unittest
from unittest.mock import MagicMock, patch

from news_agent import _build_research_prompt, _extract_json, _merge_verification, find_positive_news


class ResearchVerificationTests(unittest.TestCase):
    def test_extract_json_rejects_non_object_rows(self):
        with self.assertRaises(ValueError):
            _extract_json('[{"ok": true}, 4]')

    def test_merge_keeps_only_candidates_with_all_checks(self):
        candidates = [{"title_lt": "A", "summary_lt": "old"}, {"title_lt": "B"}]
        audits = [
            {"candidate_index": 0, "verified": True, "primary_source_verified": True,
             "claim_supported": True, "freshness_verified": True, "significance_verified": True,
             "real_world_significance_verified": True, "real_world_significance": 8,
             "progress_significance": "meaningful",
             "verification_notes": "checked", "corrected_summary_lt": "narrowed"},
            {"candidate_index": 1, "verified": True, "primary_source_verified": True,
             "claim_supported": False, "freshness_verified": True, "significance_verified": True,
             "real_world_significance_verified": True, "real_world_significance": 7,
             "progress_significance": "meaningful"},
        ]
        result = _merge_verification(candidates, audits)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["summary_lt"], "narrowed")
        self.assertEqual(result[0]["verification_status"], "verified")
        self.assertEqual(result[0]["real_world_significance"], 8)

    def test_duplicate_audit_index_fails_closed(self):
        candidates = [{"title_lt": "A"}]
        passing = {"candidate_index": 0, "verified": True, "primary_source_verified": True,
                   "claim_supported": True, "freshness_verified": True,
                   "significance_verified": True, "real_world_significance_verified": True,
                   "real_world_significance": 8, "progress_significance": "meaningful"}
        self.assertEqual(_merge_verification(candidates, [passing, passing]), [])

    def test_missing_audit_fails_closed(self):
        self.assertEqual(_merge_verification([{"title_lt": "A"}], []), [])

    def test_missing_significance_verification_fails_closed(self):
        candidates = [{"title_lt": "A"}]
        audit = {"candidate_index": 0, "verified": True, "primary_source_verified": True,
                 "claim_supported": True, "freshness_verified": True, "significance_verified": True,
                 "real_world_significance": 8, "progress_significance": "meaningful"}
        self.assertEqual(_merge_verification(candidates, [audit]), [])

    def test_temporary_red_tide_absence_fails_verification(self):
        candidates = [{"title_lt": "Red tide not detected this week"}]
        audits = [{
            "candidate_index": 0,
            "verified": True,
            "primary_source_verified": True,
            "claim_supported": True,
            "freshness_verified": True,
            "significance_verified": False,
            "real_world_significance_verified": True,
            "real_world_significance": 2,
            "progress_significance": "temporary_or_routine",
            "verification_notes": "Routine weekly non-detection only.",
        }]
        self.assertEqual(_merge_verification(candidates, audits), [])

    def test_research_prompt_uses_multi_angle_real_world_change_discovery(self):
        prompt = _build_research_prompt(72, 8, "2026-09-13T08:00:00+00:00")
        self.assertIn('Do NOT search primarily for phrases such as "positive news"', prompt)
        self.assertIn("Perform multiple independent discovery passes", prompt)
        self.assertIn("Health and medicine", prompt)
        self.assertIn("Nature and wildlife", prompt)
        self.assertIn("Climate and clean energy", prompt)
        self.assertIn("Society and public systems", prompt)
        self.assertIn("Science and technology", prompt)
        self.assertIn("implemented, took effect, approved, opened, launched, deployed", prompt)
        self.assertIn("implementation milestone rather than proof that the ecosystem has already recovered", prompt)
        self.assertIn("Do not lower evidence standards to achieve human interest", prompt)
        self.assertIn("real_world_significance", prompt)
        self.assertIn("eVTOL pilot", prompt)

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

        research_call = client.responses.create.call_args
        self.assertIn("multiple independent discovery passes", research_call.kwargs["input"])
        self.assertEqual(research_call.kwargs["tools"], [{"type": "web_search"}])


if __name__ == "__main__":
    unittest.main()
