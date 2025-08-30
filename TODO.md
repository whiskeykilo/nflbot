# Project TODOs

- One-shot mode: Add `RUN_ONCE=1` to run a single evaluation and exit instead of scheduling a loop.
- Log enrichment: Log number of games fetched, number matched to Pinnacle, number of alerts sent, and timing.
- Error context: Include brief exception messages in Discord error notifications for easier diagnosis (redact sensitive info).
- Request robustness: Add limited retries with jitter for transient network errors; fail fast on auth/4xx.
- Hard Rock adapter: Optionally support direct Hard Rock endpoints or a more resilient aggregator with rate limiting.
- Ledger semantics: Consider tracking price changes with a separate table or status updates; add indexes for analysis queries.
- Outcome tracking: Add fields/flow to record settled bets, PnL, and ROI rollups for a given bankroll policy.
- Config validation: Validate required env vars at startup and log current config (excluding secrets) for clarity.
- CLI utility: Provide a small script to query recent signals and compute basic KPIs from SQLite.
- Tests: Add an integration-style test that exercises the full run loop with mocked adapters and verifies a Discord payload.
