import argparse
import os
from collections import defaultdict
from urllib.parse import urlparse

from dotenv import load_dotenv

from news_agent import find_positive_news
from storage import fingerprint, has_seen, mark_seen
from telegram import send_telegram_message


GENERIC_PATH_MARKERS = {
    "",
    "/",
    "/news",
    "/search",
    "/aggregator",
    "/latest",
    "/home",
}

VALID_EVIDENCE_LEVELS = {
    "measured_real_world",
    "randomized_human_trial",
    "human_early_phase",
    "observational_human",
    "preclinical_animal",
    "laboratory_model",
    "policy_or_deployment",
}

VALID_IMPACT_STATUSES = {
    "measured_outcome",
    "implemented_milestone",
    "validated_research_result",
    "planned_only",
}

VALID_POSITIVE_PROGRESS = {
    "outcome_improved",
    "recovery_or_restoration",
    "effective_intervention",
    "capability_or_tool",
    "enabling_evidence",
    "problem_characterization",
}

IMPACT_BONUS = {
    "measured_outcome": 5,
    "implemented_milestone": 3,
    "validated_research_result": 1,
    "planned_only": -20,
}

PROGRESS_BONUS = {
    "outcome_improved": 4,
    "recovery_or_restoration": 4,
    "effective_intervention": 4,
    "capability_or_tool": 2,
    "enabling_evidence": 0,
    "problem_characterization": -20,
}

EVIDENCE_BONUS = {
    "measured_real_world": 3,
    "randomized_human_trial": 3,
    "policy_or_deployment": 1,
    "human_early_phase": 0,
    "observational_human": -1,
    "preclinical_animal": -3,
    "laboratory_model": -3,
}


def is_specific_source_url(url: str) -> bool:
    """Reject obvious homepages, search pages and aggregator pages."""
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return False

    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False

    path = (parsed.path or "/").rstrip("/") or "/"
    if path.lower() in GENERIC_PATH_MARKERS:
        return False

    lowered = f"{path}?{parsed.query}".lower()
    blocked_fragments = (
        "/search/",
        "?search=",
        "?q=",
        "/tag/",
        "/tags/",
        "/category/",
        "/categories/",
        "/aggregator/",
    )
    return not any(fragment in lowered for fragment in blocked_fragments)


def editorial_score(story: dict) -> int:
    """Rank strong, realized positive progress above merely promising research."""
    base = int(story.get("total_score", 0))
    evidence = (story.get("evidence_level") or "").strip().lower()
    impact = (story.get("impact_status") or "").strip().lower()
    progress = (story.get("positive_progress") or "").strip().lower()
    return (
        base
        + EVIDENCE_BONUS.get(evidence, -5)
        + IMPACT_BONUS.get(impact, -5)
        + PROGRESS_BONUS.get(progress, -5)
    )


def ordered_sources(story: dict) -> list[str]:
    """Keep the declared primary source first, then independent/supporting sources."""
    urls = [url for url in (story.get("source_urls") or []) if is_specific_source_url(url)]
    primary = (story.get("primary_source") or "").strip()
    ordered = []
    if primary and primary in urls:
        ordered.append(primary)
    ordered.extend(url for url in urls if url != primary)
    return ordered


def format_post(story: dict) -> str:
    sources = ordered_sources(story)
    source_block = "\n".join(f"Šaltinis: {url}" for url in sources[:2])
    return (
        f"{story['title_lt']}\n\n"
        f"{story['summary_lt']}\n\n"
        f"{source_block}"
    ).strip()


def run() -> None:
    min_score = int(os.getenv("MIN_SCORE", "40"))
    min_early_human_score = int(os.getenv("MIN_EARLY_HUMAN_SCORE", "45"))
    min_observational_score = int(os.getenv("MIN_OBSERVATIONAL_SCORE", "44"))
    min_weak_evidence_score = int(os.getenv("MIN_WEAK_EVIDENCE_SCORE", "47"))
    max_stories = int(os.getenv("MAX_STORIES", "3"))
    max_per_topic = int(os.getenv("MAX_PER_TOPIC", "1"))
    dry_run = os.getenv("DRY_RUN", "true").lower() == "true"

    print("Searching for strong positive-news stories...")
    stories = find_positive_news()
    stories = sorted(stories, key=editorial_score, reverse=True)
    print(f"Research returned {len(stories)} candidate(s). Applying quality gate...")

    accepted = 0
    rejected = 0
    topic_counts = defaultdict(int)

    for story in stories:
        score = int(story.get("total_score", 0))
        rank_score = editorial_score(story)
        urls = ordered_sources(story)
        primary_source = (story.get("primary_source") or "").strip()
        title = story.get("title_lt", "").strip()
        topic = (story.get("topic") or "unknown").strip().lower()
        evidence_level = (story.get("evidence_level") or "").strip().lower()
        impact_status = (story.get("impact_status") or "").strip().lower()
        positive_progress = (story.get("positive_progress") or "").strip().lower()

        reasons = []
        if not title:
            reasons.append("missing title")
        if score < min_score:
            reasons.append(f"score {score} < {min_score}")
        if not urls:
            reasons.append("no specific source URL")
        if not primary_source or not is_specific_source_url(primary_source):
            reasons.append("missing/weak primary source")
        elif primary_source not in urls:
            reasons.append("primary source not included in source_urls")
        if evidence_level not in VALID_EVIDENCE_LEVELS:
            reasons.append("missing/invalid evidence level")
        if impact_status not in VALID_IMPACT_STATUSES:
            reasons.append("missing/invalid impact status")
        elif impact_status == "planned_only":
            reasons.append("planned-only story; no realized result or implementation milestone")
        if positive_progress not in VALID_POSITIVE_PROGRESS:
            reasons.append("missing/invalid positive-progress type")
        elif positive_progress == "problem_characterization":
            reasons.append("describes a problem but does not demonstrate positive progress")

        if evidence_level == "human_early_phase" and score < min_early_human_score:
            reasons.append(f"human_early_phase requires score >= {min_early_human_score}")
        if evidence_level == "observational_human" and score < min_observational_score:
            reasons.append(f"observational_human requires score >= {min_observational_score}")
        if evidence_level in {"preclinical_animal", "laboratory_model"} and score < min_weak_evidence_score:
            reasons.append(f"{evidence_level} requires score >= {min_weak_evidence_score}")

        if topic_counts[topic] >= max_per_topic:
            reasons.append(f"topic cap reached for {topic}")
        if accepted >= max_stories:
            reasons.append(f"run cap reached ({max_stories})")

        if reasons:
            rejected += 1
            print(f"Rejected: {title or '[untitled]'} — {', '.join(reasons)}")
            continue

        fp = fingerprint(title, urls)
        if has_seen(fp):
            rejected += 1
            print(f"Skipped duplicate: {title}")
            continue

        post = format_post({**story, "source_urls": urls})
        if dry_run:
            print("\n--- CANDIDATE ---")
            print(f"Score: {score}/50")
            print(f"Editorial rank: {rank_score}")
            print(f"Topic: {topic}")
            print(f"Evidence: {evidence_level}")
            print(f"Impact: {impact_status}")
            print(f"Positive progress: {positive_progress}")
            print(f"Primary source: {primary_source}")
            print("Quality gate: PASS")
            print(post)
        else:
            send_telegram_message(post)
            mark_seen(fp, title, primary_source)
            print(f"Published: {title}")

        topic_counts[topic] += 1
        accepted += 1

    print(f"\nRun complete: {accepted} accepted, {rejected} rejected/skipped.")
    if accepted == 0:
        print("No new stories passed the quality gate.")


def test_telegram() -> None:
    send_telegram_message("✅ Glow Positive News botas prijungtas ir veikia.")
    print("Telegram test message sent.")


if __name__ == "__main__":
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-telegram", action="store_true")
    args = parser.parse_args()
    if args.test_telegram:
        test_telegram()
    else:
        run()
