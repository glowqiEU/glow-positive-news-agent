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
    max_stories = int(os.getenv("MAX_STORIES", "3"))

    prompt = f"""
You are the research editor for a Lithuanian positive-news Telegram channel.
Search the web for genuinely strong positive developments published or materially updated within the last {lookback_hours} hours.

Priorities:
- species recovery, rewilding, habitat restoration, conservation wins
- climate progress and clean energy with measurable real-world results
- medical and scientific breakthroughs with human relevance
- useful technology progress
- meaningful social progress

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

Editorial rules:
- Avoid clickbait, vague hope, PR-only claims, opinion pieces, celebrity news, sport, and trivial feel-good stories.
- Verify each story with at least 2 reliable sources when possible.
- Do not exaggerate causality or certainty.
- A story should have a concrete result, number, milestone, trial outcome, deployment, policy effect, population change, or measured improvement.
- Score each category 0-10: freshness, credibility, positive_impact, interestingness, specific_evidence.
- total_score is the sum, max 50.
- Return at most {max_stories} stories, strongest first.
- Write title_lt and summary_lt in natural Lithuanian, concise and factual.
- If a study is preliminary, laboratory-only, animal-only, observational, not yet deployed, or otherwise limited, say that clearly in summary_lt.

Return ONLY a JSON array. Each object must be:
{{
  "title_lt": "...",
  "summary_lt": "2-4 sentences",
  "topic": "wildlife|climate|energy|medicine|science|technology|society",
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
