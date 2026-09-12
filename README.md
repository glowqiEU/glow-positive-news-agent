# Glow Positive News Agent

Autonomous positive-news pipeline for sourcing, verifying, deduplicating, scoring, and publishing high-quality positive news to Telegram.

## What it does

1. Uses OpenAI web search to find recent positive developments.
2. Runs a separate source-verification pass over every candidate.
3. Prioritizes wildlife recovery, climate/clean energy, medicine, science, technology, and social progress.
4. Requires a verified primary source, underlying-development timestamp, and concrete evidence.
5. Validates every component score and the 50-point total before editorial ranking.
6. Deduplicates by event identity and canonical primary-source URL.
7. Reserves deliveries in SQLite before Telegram writes to prevent timeout-driven duplicates.
8. Publishes only when both independent safety switches are explicitly enabled.

## Local setup

```bash
git clone git@github.com:glowqiEU/glow-positive-news-agent.git
cd glow-positive-news-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and add your own secrets:

```env
OPENAI_API_KEY=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHANNEL_ID=@your_channel_username
OPENAI_MODEL=gpt-5.6-luna
DRY_RUN=true
PUBLISH_APPROVED=false
MIN_SCORE=40
MAX_STORIES=3
LOOKBACK_HOURS=72
```

Never commit `.env`.

## Test Telegram only after explicit approval

```bash
DRY_RUN=false PUBLISH_APPROVED=true python3 main.py --test-telegram
```

If everything is connected, the channel receives:

`✅ Glow Positive News botas prijungtas ir veikia.`

## Run in safe dry-run mode

Keep `DRY_RUN=true` and run:

```bash
python3 main.py
```

The agent searches and scores stories but only prints accepted candidates in the terminal.
Accepted previews are recorded in the separate `positive_news_dry_run.db` ledger,
so consecutive dry runs can exercise event-level deduplication. This preview
ledger is never consulted by live delivery and cannot suppress a later real post.
Delete only this preview database when you intentionally want to repeat dry-run
candidates from scratch.

## Enable publishing

After reviewing the results and explicitly approving publication, both safety
switches must be changed:

```env
DRY_RUN=false
PUBLISH_APPROVED=true
```

Then `python3 main.py` will publish stories that pass the quality gate. Either
switch blocks every Telegram write, including `--test-telegram`.

If Telegram delivery returns an uncertain network result, the story remains
blocked from automatic retry in SQLite. Inspect and reconcile it manually before
attempting another send; this favors avoiding duplicate public posts.

## Tests

```bash
python3 -m unittest discover -v
```

## Deployment

The intended production setup is Railway + an hourly cron job. Follow the
complete [deployment and recovery runbook](DEPLOYMENT.md). Add secrets as Railway
variables and mount persistent storage before the first run. Do not put API keys
or Telegram tokens in GitHub.
