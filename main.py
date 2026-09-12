import argparse
import os
from dotenv import load_dotenv

from news_agent import find_positive_news
from storage import fingerprint, has_seen, mark_seen
from telegram import send_telegram_message


def format_post(story: dict) -> str:
    sources = story.get("source_urls") or []
    source_block = "\n".join(f"Šaltinis: {url}" for url in sources[:2])
    return (
        f"{story['title_lt']}\n\n"
        f"{story['summary_lt']}\n\n"
        f"{source_block}"
    ).strip()


def run() -> None:
    min_score = int(os.getenv("MIN_SCORE", "40"))
    dry_run = os.getenv("DRY_RUN", "true").lower() == "true"

    stories = find_positive_news()
    accepted = 0

    for story in stories:
        score = int(story.get("total_score", 0))
        urls = story.get("source_urls") or []
        title = story.get("title_lt", "").strip()
        if not title or score < min_score or not urls:
            continue

        fp = fingerprint(title, urls)
        if has_seen(fp):
            continue

        post = format_post(story)
        if dry_run:
            print("\n--- CANDIDATE ---")
            print(f"Score: {score}/50")
            print(post)
        else:
            send_telegram_message(post)
            mark_seen(fp, title, story.get("primary_source") or urls[0])
            print(f"Published: {title}")
        accepted += 1

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
