import argparse
import os
from collections import defaultdict
from datetime import datetime, timezone

from dotenv import load_dotenv

from editorial import canonicalize_url, editorial_score, ordered_sources, rejection_reasons
from news_agent import find_positive_news
from storage import (
    complete_delivery,
    fingerprint,
    has_been_previewed,
    has_seen,
    mark_previewed,
    normalize_event_key,
    record_delivery_uncertain,
    reserve_delivery,
)
from telegram import publishing_is_approved, send_telegram_message


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
    lookback_hours = int(os.getenv("LOOKBACK_HOURS", "72"))
    dry_run = os.getenv("DRY_RUN", "true").lower() == "true"
    run_started_at = datetime.now(timezone.utc)

    if not dry_run and not publishing_is_approved():
        raise RuntimeError(
            "Live mode requested but publishing is not approved. Keep DRY_RUN=true, "
            "or set PUBLISH_APPROVED=true only after explicit editorial approval."
        )

    print("Searching for strong positive-news stories...")
    stories = find_positive_news()
    stories = sorted(stories, key=editorial_score, reverse=True)
    print(f"Research and verification returned {len(stories)} candidate(s). Applying quality gate...")

    accepted = 0
    rejected = 0
    topic_counts = defaultdict(int)
    run_event_keys = set()
    run_primary_urls = set()

    for story in stories:
        score = int(story.get("total_score", 0))
        rank_score = editorial_score(story)
        urls = ordered_sources(story)
        primary_source = canonicalize_url(story.get("primary_source") or "")
        title = story.get("title_lt", "").strip()
        topic = (story.get("topic") or "unknown").strip().lower()
        evidence_level = (story.get("evidence_level") or "").strip().lower()
        impact_status = (story.get("impact_status") or "").strip().lower()
        positive_progress = (story.get("positive_progress") or "").strip().lower()
        event_key = normalize_event_key(str(story.get("event_key") or ""))

        reasons = rejection_reasons(
            story, now=run_started_at, lookback_hours=lookback_hours,
            min_score=min_score, min_early_human_score=min_early_human_score,
            min_observational_score=min_observational_score,
            min_weak_evidence_score=min_weak_evidence_score,
        )

        if topic_counts[topic] >= max_per_topic:
            reasons.append(f"topic cap reached for {topic}")
        if accepted >= max_stories:
            reasons.append(f"run cap reached ({max_stories})")
        if event_key in run_event_keys or (primary_source and primary_source in run_primary_urls):
            reasons.append("duplicate event within current run")

        if reasons:
            rejected += 1
            print(f"Rejected: {title or '[untitled]'} — {', '.join(reasons)}")
            continue

        fp = fingerprint(title, urls)
        if has_seen(fp, event_key, primary_source):
            rejected += 1
            print(f"Skipped duplicate: {title}")
            continue
        if dry_run and has_been_previewed(fp, event_key, primary_source):
            rejected += 1
            print(f"Skipped duplicate dry-run preview: {title}")
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
            print(f"Verification: {story.get('verification_notes', '').strip()}")
            print("Quality gate: PASS")
            print(post)
            mark_previewed(fp, title, primary_source, event_key)
        else:
            if not reserve_delivery(fp, title, primary_source, event_key):
                rejected += 1
                print(f"Skipped duplicate delivery reservation: {title}")
                continue
            try:
                send_telegram_message(post)
            except Exception as exc:
                record_delivery_uncertain(fp, f"{type(exc).__name__}: {exc}")
                raise
            complete_delivery(fp)
            print(f"Published: {title}")

        topic_counts[topic] += 1
        run_event_keys.add(event_key)
        run_primary_urls.add(primary_source)
        accepted += 1

    print(f"\nRun complete: {accepted} accepted, {rejected} rejected/skipped.")
    if accepted == 0:
        print("No new stories passed the quality gate.")


def test_telegram() -> None:
    if not publishing_is_approved():
        raise RuntimeError(
            "Telegram test is a real public write and is locked without explicit approval."
        )
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
