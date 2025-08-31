# AGENTS.md — EDGErusher/NFLBot

This document is a practical operating guide for the bot-as-agent that powers EDGErusher: a lightweight NFL betting signal pipeline targeting Hard Rock Bet (Florida) with Pinnacle as the sharp reference via The Odds API. It defines the agent’s objectives, constraints, action space, data flow, component responsibilities, and runbooks for day‑to‑day use.

## 1) Agent Charter

- Objective: Continuously discover +EV NFL opportunities at Hard Rock by comparing their prices to a sharp/consensus reference (Pinnacle), compute implied probabilities and Kelly sizing, and push human‑readable recommendations to Discord.
- Human‑in‑the‑loop: The agent never auto‑places bets. It only recommends, logs, and notifies.
- Scope: NFL spreads and moneylines to start; simple containerized Python service, minimal infra.
- Cost discipline: Respect The Odds API free‑tier/rate limits via an optimized schedule and change‑detection to bank polls when the board is unchanged.
- Accountability: Persist emitted signals to SQLite for later bankroll/ROI review.

## 2) Non‑Goals

- Not a guaranteed profit engine or betting syndicate.
- Not a multi‑sport, multi‑book line‑shopping platform (initial focus is Hard Rock NFL; can extend later).
- Not heavy infrastructure: no Kubernetes, cloud scaling, or distributed systems.

## 3) Operating Constraints (Policies & Guardrails)

- No auto‑execution: Only sends Discord notifications and writes to SQLite. No sportsbook API is called for placement.
- Budget awareness: Treat The Odds API as the scarce resource; optimized schedule and movement detection reduce poll count.
- Conservatism near key numbers: EV thresholds increase for whole‑number spreads and interpolations near 3 and 7.
- Stake sizing risk cap: Fractional Kelly with an absolute unit cap (`MAX_UNIT` of bankroll).
- Persistence: All sent signals are inserted into SQLite with a unique key to prevent duplicates.
- Reliability: On reference data errors or quota events, abort the run early and optionally notify Discord with a concise status.

## 4) Action Space (What the Agent Can Do)

- Fetch current Hard Rock odds (spreads, moneylines) via an aggregator endpoint (The Odds API) configured to include Hard Rock.
- Fetch Pinnacle reference prices/alt‑line ladder via The Odds API and de‑vig to fair probabilities.
- Compute implied probabilities, EV per $1, break‑even probability, and Kelly fraction with push probability.
- Decide to alert based on configurable EV thresholds and Kelly‑derived minimum stake (>= $1).
- Send notifications to Discord via webhook (compact three‑line blocks per pick).
- Write signals to a local SQLite db at `/data/bets.sqlite`.
- Schedule next runs using an internal schedule tuned to NFL cadence.

## 5) Observations & State (What the Agent Sees/Stores)

- Observations: Current Hard Rock markets (prices + lines), Pinnacle prices and alt lines, time windows, and recent schedule tags.
- Transient state: Last sampled Hard Rock board signature for change detection.
- Persistent state: SQLite ledger of emitted signals with timestamp, pick, odds, p_true, edge, Kelly, stake, and status.
- Telemetry: Structured logs at INFO for run outcomes and DEBUG for ladder mapping details.

## 6) Data Flow

1. Hard Rock markets: Fetch upcoming NFL events (spreads and moneylines) for the next `MAX_DAYS_AHEAD` days.
2. Reference ladder: Fetch Pinnacle prices; build a favorite‑centric de‑vig probability ladder (and moneyline fair probs).
3. Mapping: Map Hard Rock’s exact line to ladder probabilities; interpolate when within `MAX_INTERP_GAP`; estimate push mass on whole numbers.
4. Valuation: Compute EV per $1 and Kelly fraction; apply dynamic EV thresholding.
5. Decision: Select best side per game and include moneylines; require EV ≥ threshold and stake ≥ $1.
6. Effects: Insert unique signals into SQLite; post compact Discord blocks; log concise per‑game context.

## 7) Component Responsibilities (Code Map)

- `app/main.py`: Orchestrates one run, optimized schedule, movement banking, decision thresholds, Discord message formatting, and persistence.
- `app/adapters/hardrock_odds.py`: Fetches Hard Rock odds via The Odds API; normalizes into `{game_id, home/away, start_utc, line_*, odds_*, ml_*}`.
- `app/adapters/reference_probs.py`: Fetches Pinnacle prices via The Odds API; de‑vigs to fair probabilities; builds alt‑line ladder and ML fair probs.
- `app/core/spreads.py`: Maps Hard Rock line to fair win/push/lose probabilities from the ladder; controls interpolation via `max_gap`.
- `app/core/ev.py`: EV math: implied probability, payout multiple, break‑even probability, and Kelly with pushes.
- `app/core/store.py`: SQLite DDL and insert with unique key on `(game_id, market, pick, odds)`.
- `app/core/notify.py`: Discord webhook POST with simple Markdown content.

## 8) Scheduling Policy

- Default: Optimized multi‑window weekly schedule tuned to NFL (inactives, final lines, island games, openers, status windows). Five‑Sunday months scale down ~20%.
- Movement banking: If the Hard Rock board signature hasn’t changed since the last sample, skip the next scheduled poll.
- Legacy: Set `USE_OPT_SCHEDULE=0` to run once per weekday and once on Sunday at configured times.

## 9) Configuration & Secrets

Required:

- `DISCORD_WEBHOOK_URL`: Discord webhook URL.
- `THEODDSAPI`: API key for The Odds API.

Core tuning (defaults shown):

- `BANKROLL=500`: Bankroll in dollars used for Kelly sizing.
- `MIN_EDGE=0.01`: Base EV threshold for spreads.
- `MIN_EDGE_ML=0.007`: Base EV threshold for moneylines.
- `KELLY_FRACTION=0.5`: Fractional Kelly multiplier.
- `MAX_UNIT=0.02`: Max stake fraction of bankroll per play.
- `MAX_DAYS_AHEAD=7`: Window of upcoming games to consider.
- `MAX_INTERP_GAP=1.0`: Max distance to allow interpolation on the ladder.

Scheduling:

- `USE_OPT_SCHEDULE=1`: Enable optimized schedule.
- `WEEKDAY_RUN_TIME=09:00`, `SUNDAY_RUN_TIME=12:00`: Legacy schedule times if `USE_OPT_SCHEDULE=0`.
- `RUN_ONCE=0|1`: If truthy, run once and exit.

Testing/diagnostics:

- `TEST_NOTIFY=0|1`: Send a “no opportunities” test message when no picks.
- `TEST_FORCE_OPPS=0|1`, `TEST_FORCE_COUNT=3`: Force top N opportunities into notifications (for formatting/Discord checks).

Security notes:

- Treat `DISCORD_WEBHOOK_URL` and `THEODDSAPI` as secrets. Do not commit or log them. Provide via environment variables or secrets manager in production.

## 10) Decision Policy Details

- EV computation: `EV = p_win * b - (1 - p_win - p_push)`, where `b` is the net payout multiple for American odds.
- Push handling: Estimate push mass from ladder slope around whole‑number spreads.
- Dynamic thresholds: Raise EV threshold to 1.5–2.0% when mapping risk is higher (whole numbers or interpolations near 3/7).
- Kelly sizing: Use Kelly with pushes and cap final stake by `MAX_UNIT * BANKROLL`; round to cents. Require stake ≥ $1.

## 11) Runbooks

Basic run (local):

1. `pip install -r app/requirements.txt`
2. Export `DISCORD_WEBHOOK_URL` and `THEODDSAPI`.
3. `RUN_ONCE=1 LOG_LEVEL=INFO python -m app.main`

Docker run:

1. Build or pull image (see README.md).
2. Mount host `./data` to container `/data`.
3. Set env vars and run container; logs to stdout.

Quota or rate limit encountered:

- Behavior: The run exits early and posts a concise “Quota” message (if webhook configured). No partial, stale, or fallback data is used.
- Operator action: Consider delaying runs, reducing schedule intensity, or upgrading plan/credits.

Empty slate (no +EV):

- Behavior: Logs “No +EV opportunities”; in `RUN_ONCE` or with `TEST_NOTIFY=1`, sends a short Discord note.
- Operator action: None required.

Troubleshooting steps:

- Verify env vars are set (`DISCORD_WEBHOOK_URL`, `THEODDSAPI`).
- Inspect logs around reference ladder building and interpolation gaps (`MAX_INTERP_GAP`).
- Check SQLite ledger at `/data/bets.sqlite` for recent inserts.
- Temporarily enable `TEST_FORCE_OPPS=1` to verify Discord formatting.

## 12) Persistence & Data Access

- SQLite path: `/data/bets.sqlite` with table `signals(id, ts, game_id, market, pick, odds, p_true, edge, kelly, stake, status)` and a uniqueness constraint on `(game_id, market, pick, odds)`.
- Suggested quick queries:
  - Recent signals: `SELECT ts, pick, odds, edge, stake FROM signals ORDER BY ts DESC LIMIT 20;`
  - ROI prep: Aggregate by week or by pick to compute realized performance once you add results marking.

## 13) Reliability & Failure Modes

- External API failures: Network errors, 4xx/5xx, schema drift — fail fast, log, and optionally notify Discord (Error/Quota titles).
- Reference mismatch: If a game lacks Pinnacle references, it is skipped; a concise error is logged if none match.
- Interpolation limits: If nearest alt lines are too far (`MAX_INTERP_GAP`), EV is not computed for that side.
- Time handling: All times are stored/sent as ISO‑UTC; Discord messages display kickoff in local time.

## 14) Ethics & Compliance

- Educational/personal use: This is a learning project to practice Python/data pipelines.
- Responsible notifications: No promises of profitability. Users evaluate risk and execute manually.
- Respect ToS/robots: Do not scrape prohibited endpoints; current setup uses The Odds API with attribution and keys.

## 15) Extensibility Guidelines

- New markets/sports: Add an adapter for the target book, extend mapping logic if lines differ (e.g., totals), and update selection policy.
- Alternate references: Add new reference providers behind `reference_probs_for(...)` with a consistent fair‑probability contract.
- Modeling: Introduce ML‑based priors as an additional reference channel; merge with market‑implied priors conservatively.
- UI/ops: Add CLI utilities for querying the ledger, health checks, and lightweight dashboards if desired.
