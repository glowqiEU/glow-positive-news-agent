import unittest

from news_agent import _extract_json, _merge_verification


class ResearchVerificationTests(unittest.TestCase):
    def test_extract_json_rejects_non_object_rows(self):
        with self.assertRaises(ValueError):
            _extract_json('[{"ok": true}, 4]')

    def test_merge_keeps_only_candidates_with_all_checks(self):
        candidates = [{"title_lt": "A", "summary_lt": "old"}, {"title_lt": "B"}]
        audits = [
            {"candidate_index": 0, "verified": True, "primary_source_verified": True,
             "claim_supported": True, "freshness_verified": True,
             "verification_notes": "checked", "corrected_summary_lt": "narrowed"},
            {"candidate_index": 1, "verified": True, "primary_source_verified": True,
             "claim_supported": False, "freshness_verified": True},
        ]
        result = _merge_verification(candidates, audits)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["summary_lt"], "narrowed")
        self.assertEqual(result[0]["verification_status"], "verified")

    def test_duplicate_audit_index_fails_closed(self):
        candidates = [{"title_lt": "A"}]
        passing = {"candidate_index": 0, "verified": True, "primary_source_verified": True,
                   "claim_supported": True, "freshness_verified": True}
        self.assertEqual(_merge_verification(candidates, [passing, passing]), [])

    def test_missing_audit_fails_closed(self):
        self.assertEqual(_merge_verification([{"title_lt": "A"}], []), [])


if __name__ == "__main__":
    unittest.main()
