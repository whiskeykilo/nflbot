# AGENTS.md — EDGErusher/NFLBot

Short, project-specific notes for working in this repo.

## Core objective (why)
- Find +EV NFL spots at Hard Rock by comparing to Pinnacle via The Odds API, then notify Discord and log to SQLite (no auto-betting). This keeps the project aligned with its human‑in‑the‑loop, lightweight signal focus.

## Guardrails that matter (why)
- **No auto-execution:** Only recommend, notify, and log. This is a compliance/ethics boundary.
- **API budget is scarce:** Prefer change-detection and optimized schedules to limit The Odds API calls.
- **Conservative near key numbers:** Increase EV thresholds around whole numbers and 3/7 because mapping risk is higher.
- **Kelly risk cap:** Use fractional Kelly and cap stake by `MAX_UNIT` of bankroll to control drawdowns.
- **Persist signals:** Insert into SQLite with a uniqueness key to avoid duplicate alerts.
- **Fail fast on reference errors/quota:** Abort run and optionally notify to avoid acting on stale or partial data.

## Code map (where to look)
- Orchestration + scheduling + decisions: `app/main.py`
- Hard Rock odds adapter: `app/adapters/hardrock_odds.py`
- Pinnacle reference + de‑vig ladder: `app/adapters/reference_probs.py`
- Spread mapping/interpolation: `app/core/spreads.py`
- EV + Kelly math: `app/core/ev.py`
- SQLite store + uniqueness: `app/core/store.py`
- Discord notifications: `app/core/notify.py`

## Commands you’ll actually use (how)
- Local run: `RUN_ONCE=1 LOG_LEVEL=INFO python -m app.main`
- Install deps: `pip install -r app/requirements.txt`

## Required secrets (why)
- `DISCORD_WEBHOOK_URL`, `THEODDSAPI` must be provided via env vars. Don’t commit or log them.

## Quick debugging cues (why)
- Ladder mapping gaps: check `MAX_INTERP_GAP` usage and logs around reference ladder building.
- No +EV: expected; use `TEST_FORCE_OPPS=1` for Discord formatting checks.

## Cursor Cloud specific instructions

- **Python 3.12** is pre-installed; use `python3` (not `python`) to invoke.
- **Lint:** `flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics` (critical errors only, matches CI). The full style pass with `--exit-zero` produces ~250 warnings and is non-blocking.
- **Tests:** `pytest -v` — all 33 tests are fully mocked (no network or API key needed). Run from repo root.
- **Live run:** `RUN_ONCE=1 LOG_LEVEL=INFO TEST_FORCE_OPPS=1 python3 -m app.main` — requires `THEODDSAPI` and `DISCORD_WEBHOOK_URL` env vars plus egress to `api.the-odds-api.com` and `discord.com`. The Cloud VM's egress restrictions may block these domains; the app handles the failure gracefully (logs + Discord error notification attempt).
- **SQLite data dir:** The app writes to `/data/bets.sqlite`. Run `sudo mkdir -p /data && sudo chmod 777 /data` before a live run. Tests create their own temp DBs.
- **PATH:** User-installed pip scripts land in `~/.local/bin` which may not be on `PATH`. Prefix commands with `export PATH="$HOME/.local/bin:$PATH"` or run tools via `python3 -m pytest`, `python3 -m flake8`.
