# NFLBot 🏈

Scan Hard Rock NFL spreads against a sharp reference (Pinnacle), compute no‑vig probabilities at your exact line (with pushes), size via Kelly, and post concise +EV picks to Discord.

---

## Features

- Markets: Hard Rock spreads (point handicaps) with American prices.
- Reference: Pinnacle spreads with alternate lines (ATS). De‑vig each line to fair probabilities.
- Mapping: Interpolate Pinnacle’s alt‑line ladder to Hard Rock’s exact spread; account for pushes on whole numbers.
- EV: Expected value per $1 stake; dynamic EV threshold based on mapping risk.
- Sizing: Kelly fraction with push probability; cap by `MAX_UNIT`.
- Persistence: Signals saved to SQLite (`/data/bets.sqlite`).
- Scheduling: Optimized in‑app schedule to fit monthly poll budget; no host cron needed.
- Notifications: Discord webhook with readable, compact format.

## Scheduling

By default the bot installs an optimized weekly schedule (~248 polls/month) focused on the highest‑signal windows:

- Sunday 1pm slate: Inactives 11:30–11:45 (8 polls), final 12:30–12:59 (12)
- Sunday 4:25pm slate: Inactives 14:55–15:10 (6), final 16:05–16:25 (4)
- SNF/MNF/TNF: 6 polls each T−75 to T−10
- Sunday night openers: 6 polls 20:00–23:00
- Friday status: 4 polls 15:30–18:30
- Saturday limits rise: 4 polls 18:00–23:30

Behavior:
- Five‑Sunday months: buckets scale ~20% down automatically.
- Banking: if the Hard Rock board hasn’t moved since the last sample, skip the next scheduled poll to preserve budget.

Controls:
- `USE_OPT_SCHEDULE=0` switches to a simple legacy schedule with `WEEKDAY_RUN_TIME` and `SUNDAY_RUN_TIME`.

---

## Quick Start

### 1. Use the prebuilt GHCR image (recommended)

Pull the image published by GitHub Actions to GitHub Container Registry (GHCR).

```bash
docker pull ghcr.io/<owner>/<repo>:latest
# Example if your repo is github.com/acme/nflbot
# docker pull ghcr.io/acme/nflbot:latest
```

Then run it as shown below in Step 4, replacing the image name with
`ghcr.io/<owner>/<repo>:<tag>` (e.g., `latest` or a version tag).

Notes:
- Repositories are published to GHCR by the workflow on pushes to `main` and tags `v*.*.*`.
- If the package is private, authenticate first: `echo $GITHUB_TOKEN | docker login ghcr.io -u <your-username> --password-stdin`.

### Or, build the image locally

```bash
docker build -t nflbot:0.1.0 .
```

### 2. Configure the Discord webhook

Set `DISCORD_WEBHOOK_URL` to a Discord webhook before running the bot:

```bash
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
```

### 3. Configure The Odds API (required for alerts)

Set `THEODDSAPI` with your API key. The bot fetches Pinnacle spreads (with alt lines) and removes vig to compute fair probabilities. If this fetch fails or quota is exhausted, the run exits early (optionally sends a “Quota” notice to Discord) and will resume on the next scheduled poll.

```bash
export THEODDSAPI="<your_api_key>"
```

### 4. Run the container

Mount a host directory for the SQLite ledger at `/data` and pass the webhook
URL (and any tuning variables) as environment variables.

```bash
docker run --name nflbot \
  -e DISCORD_WEBHOOK_URL="$DISCORD_WEBHOOK_URL" \
  -e BANKROLL=500 -e MIN_EDGE=0.01 -e KELLY_FRACTION=0.5 -e MAX_UNIT=0.02 \
  -e USE_OPT_SCHEDULE=1 -e WEEKDAY_RUN_TIME=09:00 -e SUNDAY_RUN_TIME=12:00 \
  -e THEODDSAPI="${THEODDSAPI:-}" \
  -v $(pwd)/data:/data \
  --restart unless-stopped \
  nflbot:0.1.0
```

The bot self-schedules using the `schedule` library and does not require a host
cron or compose setup. Logs print to stdout.

---

## Configuration

- `DISCORD_WEBHOOK_URL`: Discord webhook (required to send alerts).
- `BANKROLL`: Total bankroll in dollars (default `500`).
- `MIN_EDGE`: Base EV threshold (decimal). Default `0.01` (1%).
- `KELLY_FRACTION`: Fractional Kelly to apply (default `0.5`).
- `MAX_UNIT`: Max stake as fraction of bankroll (default `0.02`).
- `MAX_INTERP_GAP`: Max points away for interpolation (default `1.0`).
- `USE_OPT_SCHEDULE`: Enable optimized weekly schedule (default `1`).
- `WEEKDAY_RUN_TIME` / `SUNDAY_RUN_TIME`: Legacy schedule times in `HH:MM`.
- `THEODDSAPI`: API key for Pinnacle reference prices.
- `RUN_ONCE`: If truthy, runs once and exits.

Notes:
- Dynamic EV thresholding raises the bar to 1.5–2.0% in riskier mappings (whole numbers or interpolations near 3/7).
- Signals are de‑duplicated in SQLite via a unique key.

SQLite ledger is written to `/data/bets.sqlite`. Mount `/data` to persist.

---

## Discord Output

Each alert is a compact three‑line block:

```
SF @ JAX — Sun 13:00 👊 +0.7% EV
* Pick: JAX +7.5 at -115 (Hard Rock)
* Stake: $5.00
```

### De-duplication

Identical signals are de-duplicated in the ledger using a unique key on
`(game_id, market, pick, odds)`. Repeated runs that encounter the same price
for the same side will not create duplicate rows.

---

## Development & Testing

- Install: `pip install -r app/requirements.txt`
- Run once: `RUN_ONCE=1 LOG_LEVEL=INFO python -m app.main`
- Tests: `pytest -q`

Notes:
- Quota handling: if The Odds API returns 402/429 or equivalent, the run exits early and posts a concise “Quota” message to Discord (if configured).
- Logging includes a brief per‑game note when EV is unavailable due to insufficient Pinnacle alt lines within `MAX_INTERP_GAP`.
