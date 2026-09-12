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

WEAK_EVIDENCE_LEVELS = {
    "preclinical_animal",
    "laboratory_model",
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


def format_post(story: dict) -> str:
    sources = [url for url in (story.get("source_urls") or []) if is_specific_source_url(url)]
    source_block = "\n".join(f"Šaltinis: {url}" for url in sources[:2])
    return (
        f"{story['title_lt']}\n\n"
        f"{story['summary_lt']}\n\n"
        f"{source_block}"
    ).strip()


def run() -> None:
    min_score = int(os.getenv("MIN_SCORE", "40"))
    min_weak_evidence_score = int(os.getenv("MIN_WEAK_EVIDENCE_SCORE", "45"))
    max_stories = int(os.getenv("MAX_STORIES", "3"))
    max_per_topic = int(os.getenv("MAX_PER_TOPIC", "1"))
    dry_run = os.getenv("DRY_RUN", "true").lower() == "true"

    print("Searching for strong positive-news stories...")
    stories = find_positive_news()
    stories = sorted(stories, key=lambda s: int(s.get("total_score", 0)), reverse=True)
    print(f"Research returned {len(stories)} candidate(s). Applying quality gate...")

    accepted = 0
    rejected = 0
    topic_counts = defaultdict(int)

    for story in stories:
        score = int(story.get("total_score", 0))
        urls = [url for url in (story.get("source_urls") or []) if is_specific_source_url(url)]
        primary_source = (story.get("primary_source") or "").strip()
        title = story.get("title_lt", "").strip()
        topic = (story.get("topic") or "unknown").strip().lower()
        evidence_level = (story.get("evidence_level") or "").strip().lower()
        impact_status = (story.get("impact_status") or "").strip().lower()

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
        if evidence_level in WEAK_EVIDENCE_LEVELS and score < min_weak_evidence_score:
            reasons.append(
                f"{evidence_level} requires score >= {min_weak_evidence_score}"
            )
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
            print(f"Topic: {topic}")
            print(f"Evidence: {evidence_level}")
            print(f"Impact: {impact_status}")
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
