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

- `python3 -m unittest discover -v`: 21 tests passing.
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

## Next action

Run several API-backed dry runs with `DRY_RUN=true`, review false positives and rejection reasons, then add bounded research retry/backoff and fixture-based end-to-end pipeline tests before considering any publication approval.
