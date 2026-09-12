import json
import os
import re
from typing import Any

from openai import OpenAI


def _extract_json(text: str) -> list[dict[str, Any]]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("Expected a JSON array from the model")
    return data


def find_positive_news() -> list[dict[str, Any]]:
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    model = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
    lookback_hours = int(os.getenv("LOOKBACK_HOURS", "72"))
    max_candidates = int(os.getenv("MAX_RESEARCH_STORIES", "8"))

    prompt = f"""
You are the research editor for a Lithuanian positive-news Telegram channel.
Search the web for genuinely strong positive developments published or materially updated within the last {lookback_hours} hours.

Priorities:
- species recovery, rewilding, habitat restoration, conservation wins
- climate progress and clean energy with measurable real-world results
- medical and scientific breakthroughs with human relevance
- useful technology progress
- meaningful social progress

Diversity rules:
- Search broadly across the priority areas instead of filling the result set with one field.
- When several stories have similar quality, prefer topic diversity.
- Return a candidate pool, not three near-duplicates from the same research beat.

Freshness rules:
- Prefer developments whose underlying event, result, study publication, official announcement, deployment, policy effect, or measured milestone is genuinely recent.
- Do NOT treat an old event as fresh merely because a website republished, syndicated, summarized, or resurfaced it recently.
- If the underlying result is old and there is no meaningful new update, exclude it.

Source rules:
- Every returned story MUST include at least one real primary source that directly supports the central claim.
- Primary sources include: the original peer-reviewed paper, official government or public-agency release, university or hospital announcement tied to the research, official project/conservation organization update, or the organization directly responsible for the measured result.
- Do not use homepages, category pages, search pages, tag pages, generic news aggregators, or RSS/aggregator pages as evidence URLs.
- Prefer a second independent reliable source when possible.
- source_urls must be direct URLs to the exact supporting article, paper, report, release, or project update.
- primary_source must be one of the URLs in source_urls.

Evidence-level rules:
Assign exactly one evidence_level:
- measured_real_world: measured population, environmental, infrastructure, economic, public-health, or other real-world outcome
- randomized_human_trial: randomized human trial with a clinically meaningful outcome
- human_early_phase: early human safety, biomarker, feasibility, or small proof-of-concept study
- observational_human: non-randomized human observational evidence
- preclinical_animal: animal-only evidence
- laboratory_model: cells, organoids, chips, materials, simulations, or other laboratory-only evidence
- policy_or_deployment: a policy, regulation, infrastructure deployment, or program implementation with concrete scope, even if long-term outcome data are not yet available

Impact-status rules:
Assign exactly one impact_status:
- measured_outcome: a positive outcome has already been measured in the real world
- implemented_milestone: a concrete implementation, launch, approval, restoration action, infrastructure milestone, or policy change has already happened
- validated_research_result: a study has produced a concrete supported result, even if clinical or real-world impact is not yet established
- planned_only: funding, agreement, target, intention, future rollout, proposal, or plan without a substantive outcome or implementation milestone yet

A story labeled planned_only is generally NOT suitable for publication. Funding announcements, partnerships, signed agreements, targets such as "will reach 100 million people", and future programs are not positive outcomes by themselves. Prefer what has actually changed, improved, recovered, been built, deployed, approved, measured, or demonstrated.

Editorial rules:
- Avoid clickbait, vague hope, PR-only claims, opinion pieces, celebrity news, sport, and trivial feel-good stories.
- Verify each story with at least 2 reliable sources when possible.
- Do not exaggerate causality or certainty.
- A story should have a concrete result, number, milestone, trial outcome, deployment, policy effect, population change, or measured improvement.
- Score each category 0-10: freshness, credibility, positive_impact, interestingness, specific_evidence.
- total_score is the sum, max 50.
- Return at most {max_candidates} stories, strongest first.
- Write title_lt and summary_lt in natural Lithuanian, concise and factual.
- If evidence is preliminary, laboratory-only, animal-only, observational, not yet deployed, or otherwise limited, say that clearly in summary_lt.
- Do not describe a biomarker change as a proven patient benefit.
- Do not describe a laboratory model as a treatment or breakthrough for patients.
- Do not award a high positive_impact score merely for a large promised future reach; score realized or demonstrated impact more highly than ambition.

Return ONLY a JSON array. Each object must be:
{{
  "title_lt": "...",
  "summary_lt": "2-4 sentences",
  "topic": "wildlife|climate|energy|medicine|science|technology|society",
  "evidence_level": "measured_real_world|randomized_human_trial|human_early_phase|observational_human|preclinical_animal|laboratory_model|policy_or_deployment",
  "impact_status": "measured_outcome|implemented_milestone|validated_research_result|planned_only",
  "freshness": 0,
  "credibility": 0,
  "positive_impact": 0,
  "interestingness": 0,
  "specific_evidence": 0,
  "total_score": 0,
  "key_number": "short concrete number or milestone",
  "source_urls": ["https://exact-source-page...", "https://exact-second-source-page..."],
  "primary_source": "https://exact-primary-source-page..."
}}
"""

    response = client.responses.create(
        model=model,
        tools=[{"type": "web_search"}],
        input=prompt,
    )
    return _extract_json(response.output_text)
