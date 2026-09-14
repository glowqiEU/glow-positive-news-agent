from datetime import datetime, timezone
import unittest

from editorial import canonicalize_url, component_score, ordered_sources, rejection_reasons

NOW = datetime(2026, 9, 12, 12, tzinfo=timezone.utc)


def valid_story():
    return {
        "title_lt": "Atkurtame pelkyne sugrįžo reta rūšis",
        "summary_lt": "Oficiali stebėsena patvirtino pamatuotą rezultatą.",
        "topic": "wildlife", "evidence_level": "measured_real_world",
        "impact_status": "measured_outcome", "positive_progress": "recovery_or_restoration",
        "progress_significance": "meaningful", "real_world_significance": 8,
        "freshness": 9, "credibility": 9, "positive_impact": 8,
        "interestingness": 7, "specific_evidence": 9, "total_score": 42,
        "development_at": "2026-09-11T15:00:00Z",
        "source_urls": ["https://www.agency.example/report/123?utm_source=x", "https://news.example/story"],
        "primary_source": "https://agency.example/report/123",
        "primary_source_type": "government_or_public_agency",
        "primary_evidence": "The agency reports the measured return.",
        "event_key": "agency-rare-species-return-2026-09-11",
        "verification_status": "verified",
        "verification_notes": "Primary agency report supports the result and date.",
    }


def reasons(story):
    return rejection_reasons(story, now=NOW, lookback_hours=72, min_score=40,
                             min_early_human_score=45, min_observational_score=44,
                             min_weak_evidence_score=47, min_real_world_significance=6)


class EditorialValidationTests(unittest.TestCase):
    def test_valid_candidate_passes(self):
        self.assertEqual(reasons(valid_story()), [])

    def test_rejects_stale_underlying_development(self):
        story = valid_story(); story["development_at"] = "2026-09-01T12:00:00Z"
        self.assertIn("underlying development older than 72h", reasons(story))

    def test_rejects_timestamp_without_timezone(self):
        story = valid_story(); story["development_at"] = "2026-09-12"
        self.assertIn("missing/invalid development timestamp", reasons(story))

    def test_total_score_from_model_is_not_trusted(self):
        story = valid_story(); story["total_score"] = 57
        self.assertEqual(component_score(story), 42)
        self.assertEqual(reasons(story), [])

    def test_rejects_invalid_component_score(self):
        story = valid_story(); story["freshness"] = 11
        self.assertIn("component score outside 0-10", reasons(story))

    def test_requires_primary_evidence_metadata(self):
        story = valid_story(); story["primary_source_type"] = "news_article"; story["primary_evidence"] = ""
        result = reasons(story)
        self.assertIn("missing/invalid primary source type", result)
        self.assertIn("missing primary-source evidence note", result)

    def test_canonicalizes_tracking_and_source_order(self):
        self.assertEqual(canonicalize_url("https://WWW.Example.com/a/?utm_medium=social&b=2&a=1#x"), "https://example.com/a?a=1&b=2")
        self.assertEqual(ordered_sources(valid_story())[0], "https://agency.example/report/123")

    def test_rejects_problem_characterization(self):
        story = valid_story(); story["positive_progress"] = "problem_characterization"
        self.assertTrue(any("does not demonstrate positive progress" in item for item in reasons(story)))

    def test_rejects_routine_temporary_absence_of_harm(self):
        story = valid_story()
        story["title_lt"] = "Šią savaitę Floridoje raudonojo potvynio neaptikta"
        story["summary_lt"] = "Rutininė savaitinė stebėsena organizmo neaptiko."
        story["positive_progress"] = "outcome_improved"
        story["progress_significance"] = "temporary_or_routine"
        self.assertIn(
            "temporary absence or routine status is not strong positive progress",
            reasons(story),
        )

    def test_rejects_low_real_world_significance(self):
        story = valid_story()
        story["topic"] = "technology"
        story["evidence_level"] = "policy_or_deployment"
        story["impact_status"] = "implemented_milestone"
        story["positive_progress"] = "capability_or_tool"
        story["real_world_significance"] = 5
        self.assertIn("real_world_significance 5 < 6", reasons(story))

    def test_requires_real_world_significance(self):
        story = valid_story()
        story.pop("real_world_significance")
        self.assertIn("missing/invalid real-world significance score", reasons(story))

    def test_human_early_phase_score_44_is_rejected(self):
        story = valid_story()
        story.update({
            "evidence_level": "human_early_phase",
            "impact_status": "validated_research_result",
            "positive_progress": "enabling_evidence",
            "freshness": 9,
            "credibility": 9,
            "positive_impact": 8,
            "interestingness": 9,
            "specific_evidence": 9,
            "total_score": 50,
            "summary_lt": "Nedidelis ankstyvos fazės tyrimas pateikė preliminarų rezultatą; klinikinė nauda dar neįrodyta.",
        })
        self.assertIn("human_early_phase requires score >= 45", reasons(story))

    def test_human_early_phase_score_45_remains_eligible_when_other_gates_pass(self):
        story = valid_story()
        story.update({
            "evidence_level": "human_early_phase",
            "impact_status": "validated_research_result",
            "positive_progress": "enabling_evidence",
            "freshness": 9,
            "credibility": 9,
            "positive_impact": 8,
            "interestingness": 9,
            "specific_evidence": 10,
            "total_score": 1,
            "summary_lt": "Nedidelis ankstyvos fazės tyrimas pateikė preliminarų rezultatą; klinikinė nauda dar neįrodyta.",
        })
        self.assertEqual(reasons(story), [])


if __name__ == "__main__":
    unittest.main()
