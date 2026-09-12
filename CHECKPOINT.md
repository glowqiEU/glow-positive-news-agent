# Development checkpoint

Updated: 2026-09-12 UTC

## Safety state

- `DRY_RUN=true` remains the documented default.
- `PUBLISH_APPROVED=false` is required by default.
- No Telegram or other public publication was performed during this work.
- A live write requires both `DRY_RUN=false` and `PUBLISH_APPROVED=true`.

## Incremental commits

- `d5c4322` — fail-closed Telegram publication boundary and message validation.
- `0b2001f` — deterministic freshness, evidence metadata, URL, and score gates.
- `7dd71a7` — event/source deduplication and backward-compatible SQLite migration.
- `0394ba7` — separate, fail-closed primary-source and claim verification pass.
- `9fb3d9c` — pre-send delivery reservations and uncertain-delivery quarantine.

## Verification performed

- `python3 -m unittest discover -v`: 25 tests passing.
- `python3 -m compileall`: passing for application and test modules.
- `git diff --check`: passing.
- No live research run: this workspace has no `OPENAI_API_KEY`.
- No Telegram integration test: public writes are intentionally locked and were not approved.

## Remaining risks

- The discovery and verification passes use the configured OpenAI model; their real-world quality still needs reviewed dry-run samples.
- No deterministic fetch/content parser independently compares source text with every claim; the second web-search pass is the current verification layer.
- Event-level semantic deduplication depends partly on a stable model-generated `event_key`.
- Delivery rows marked `uncertain` require manual reconciliation because Telegram's send API does not provide an idempotency key.
- API retry/backoff and structured operational run logs are not yet implemented.

## QA follow-up: repeated preview and weak transient progress

- Dry-run candidates now use a separate `positive_news_dry_run.db` ledger, allowing
  consecutive runs to validate event/source deduplication without writing to or
  suppressing stories in the production delivery database.
- `progress_significance` now distinguishes meaningful progress from temporary or
  routine status. Weekly non-detection, normal conditions, and “nothing bad
  happened” are rejected unless sources establish sustained recovery, a meaningful
  trend, or clearly consequential improvement.
- Both discovery and independent verification prompts enforce this distinction;
  deterministic validation rejects `temporary_or_routine` candidates.

## Next action

Run two consecutive API-backed dry runs with `DRY_RUN=true` to confirm that an
accepted first-run event is skipped from the preview ledger on the second run,
and confirm transient routine-status candidates are rejected. Publishing remains
out of scope.

## Final pre-production audit

### Blockers before deployment

- Attach persistent storage and set `DATABASE_PATH` and `DRY_RUN_DB_PATH` to
  absolute paths on that volume; relative SQLite files are not deployment-safe.
- Configure the bounded OpenAI timeout/retry settings and verify scheduled-run
  logs are visible.
- Deploy one replica only and prove database persistence with a restart/redeploy
  while publication remains disabled.

### Safe-to-defer improvements

- Structured JSON logging and external alerting beyond platform run status.
- A deterministic source-text-to-claim parser in addition to the independent
  web-search verification pass.
- More sophisticated semantic deduplication beyond event keys and canonical URLs.
- Reconsidering the `human_early_phase` policy after more QA samples. The current
  45/50 threshold remains unchanged because present evidence does not justify a
  stricter rule.

### Reliability controls added

- Persistent production database path through `DATABASE_PATH`.
- SQLite WAL mode, 30-second busy timeout, and existing atomic delivery reservation.
- Explicit 180-second OpenAI request timeout with two SDK retries by default.
- Telegram network errors are sanitized so bot tokens cannot leak into logs or
  uncertain-delivery records.
- Read-only uncertain-delivery listing and explicit `published`/`retry` resolution.
- Exact deployment, restart, recovery, and publication gates in `DEPLOYMENT.md`.
