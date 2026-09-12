# Glow Positive News Agent

Autonomous positive-news pipeline for sourcing, verifying, deduplicating, scoring, and publishing high-quality positive news to Telegram.

## What it does

1. Uses OpenAI web search to find recent positive developments.
2. Prioritizes wildlife recovery, climate/clean energy, medicine, science, technology, and social progress.
3. Requires concrete evidence and reliable sources.
4. Scores every story out of 50.
5. Rejects weak stories below `MIN_SCORE`.
6. Tracks already-published stories in SQLite.
7. Publishes accepted stories to Telegram.

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
MIN_SCORE=40
MAX_STORIES=3
LOOKBACK_HOURS=72
```

Never commit `.env`.

## Test Telegram first

```bash
python3 main.py --test-telegram
```

If everything is connected, the channel receives:

`✅ Glow Positive News botas prijungtas ir veikia.`

## Run in safe dry-run mode

Keep `DRY_RUN=true` and run:

```bash
python3 main.py
```

The agent searches and scores stories but only prints accepted candidates in the terminal.

## Enable publishing

After reviewing the first results, change:

```env
DRY_RUN=false
```

Then `python3 main.py` will publish stories that pass the quality gate.

## Deployment

The intended production setup is Railway + an hourly cron job. Add the same environment variables as Railway secrets. Do not put API keys or Telegram tokens in GitHub.
