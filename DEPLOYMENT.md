# Railway deployment runbook

Publishing must remain disabled throughout initial deployment and restart testing.

## 1. Create the service

1. Create a Railway service from `glowqiEU/glow-positive-news-agent`, branch `main`.
2. Use `python3 main.py` as the start command.
3. Run exactly one replica. SQLite and the delivery reservation model are not a
   multi-replica database design.
4. Configure the cron schedule in UTC. Start with `0 * * * *` for hourly runs.

## 2. Attach persistent storage

1. Attach a Railway volume to the service at `/data` before the first run.
2. Set these variables exactly:

```env
DATABASE_PATH=/data/positive_news.db
DRY_RUN_DB_PATH=/data/positive_news_dry_run.db
```

Both files must survive a redeploy/restart. Never place either database only on
the ephemeral application filesystem.

## 3. Configure initial variables

```env
OPENAI_API_KEY=<secret>
OPENAI_MODEL=gpt-5.6-luna
OPENAI_TIMEOUT_SECONDS=180
OPENAI_MAX_RETRIES=2
DRY_RUN=true
PUBLISH_APPROVED=false
MIN_SCORE=40
MIN_EARLY_HUMAN_SCORE=45
MIN_OBSERVATIONAL_SCORE=44
MIN_WEAK_EVIDENCE_SCORE=47
MAX_STORIES=3
MAX_RESEARCH_STORIES=8
MAX_PER_TOPIC=1
LOOKBACK_HOURS=72
```

Store all secrets as Railway variables. Do not commit `.env`. Telegram credentials
may be configured before launch, but both publication switches must remain locked.

## 4. Pre-production verification

1. Run the full test suite in the deployed build:

```bash
python3 -m unittest discover -v
python3 -m compileall -q main.py news_agent.py editorial.py storage.py telegram.py tests
git diff --check
```

2. Execute at least two scheduled dry runs. Confirm the first accepted event is
   recorded and the second occurrence prints `Skipped duplicate dry-run preview`.
3. Confirm transient/routine non-events such as a single weekly red-tide
   non-detection do not appear as accepted candidates.
4. Restart or redeploy the service, then run again and confirm preview deduplication
   still works. This proves `/data` is actually persistent.
5. Review logs for API timeouts, malformed JSON, source-verification failures, and
   rejected candidates. Any failure must end the run without a Telegram write.

## 5. Uncertain-delivery recovery

List quarantined deliveries:

```bash
python3 main.py --list-uncertain
```

After manually checking the Telegram channel, resolve exactly one fingerprint:

```bash
python3 main.py --resolve-uncertain <fingerprint> --resolution published
```

Use `--resolution retry` only after confirming the message is absent from Telegram.
That releases the deduplication reservation and allows a later run to send it.

## 6. Conditions before publication

Do not enable publication until all of these are true:

- The persistent volume survives a tested restart/redeploy.
- Multiple reviewed API-backed dry runs show acceptable factual and editorial quality.
- Primary-source, freshness, significance, and event-deduplication checks behave as expected.
- `python3 main.py --list-uncertain` returns an empty array.
- The exact Telegram channel ID and bot permissions have been manually verified.
- Operational logs are visible and failed cron runs can be noticed promptly.
- A human has explicitly approved enabling publication.

Only then, in one controlled change, set both:

```env
DRY_RUN=false
PUBLISH_APPROVED=true
```

Changing only one switch must continue to block all Telegram writes.
