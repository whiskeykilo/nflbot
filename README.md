# NFLBot 🏈

A minimal Python container that scans **Hard Rock NFL odds** against a sharp/consensus reference,
flags +EV bets, and pushes them to Discord for human review.

---

## Features

- Pull NFL moneyline odds (Hard Rock adapter stub included — swap in a real API/scraper).
- Compare against sharp/consensus reference probabilities (vig-removed).
- Calculate expected value (+EV), Kelly fraction, and recommended stake.
- Persist signals to a local SQLite ledger (`/data/bets.sqlite`).
- Schedule internally (via `schedule` lib) — no host cron or docker-compose needed.
  Configure run times with `SUNDAY_RUN_TIME` and `WEEKDAY_RUN_TIME` env vars.
- Push alerts to a Discord channel using a webhook.

## Scheduling

Runs every day at `WEEKDAY_RUN_TIME` and an additional run on Sundays at
`SUNDAY_RUN_TIME`. Times use 24h `HH:MM` format.

---

## Quick Start

### 1. Build the image

```bash
docker build -t nflbot:3.12 .
```

### 2. Configure the Discord webhook

Set `DISCORD_WEBHOOK_URL` to a Discord webhook before running the bot:

```bash
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
```

### 3. Configure The Odds API (required for alerts)

Set `THEODDSAPI` with your API key to fetch Pinnacle moneyline odds for
vig-removed reference probabilities. If this fetch fails or the key is missing,
the run aborts and a Discord error is posted (no signals are sent).

```bash
export THEODDSAPI="<your_api_key>"
```

### 4. Run the container

Mount a host directory for the SQLite ledger at `/data` and pass the webhook
URL (and any tuning variables) as environment variables.

```bash
docker run --name nflbot \
  -e DISCORD_WEBHOOK_URL="$DISCORD_WEBHOOK_URL" \
  -e BANKROLL=500 -e MIN_EDGE=0.03 -e KELLY_FRACTION=0.5 -e MAX_UNIT=0.02 \
  -e WEEKDAY_RUN_TIME=09:00 -e SUNDAY_RUN_TIME=12:00 \
  -e THEODDSAPI="${THEODDSAPI:-}" \
  -v $(pwd)/data:/data \
  --restart unless-stopped \
  nflbot:3.12
```

The bot self-schedules using the `schedule` library and does not require a host
cron or compose setup. Logs print to stdout.

---

## Configuration

- `DISCORD_WEBHOOK_URL`: Discord webhook (required to send alerts).
- `BANKROLL`: Total bankroll in dollars (default `500`).
- `MIN_EDGE`: Minimum EV threshold per $1 (e.g., `0.03` = 3%).
- `KELLY_FRACTION`: Fractional Kelly to apply (default `0.5`).
- `MAX_UNIT`: Max stake as fraction of bankroll (default `0.02`).
- `WEEKDAY_RUN_TIME`: Daily run time in `HH:MM` 24h format (default `09:00`).
- `SUNDAY_RUN_TIME`: Additional Sunday run time (default `12:00`).
- `THEODDSAPI`: API key for Pinnacle reference prices (required for alerts).
- `RUN_ONCE`: If set (e.g., `1`), runs a single evaluation and exits instead of scheduling.

SQLite ledger is written to `/data/bets.sqlite`. Mount a volume at `/data`
to persist across container restarts.

---

## Manual Trigger via Discord (optional)

You can trigger an immediate run by sending `run`, `!run`, or `/run` in a specific
Discord channel. This keeps the human in the loop and allows ad‑hoc refreshes.

Requirements:

- A Discord bot with message content intent enabled.
- The bot must be in your server and able to read the target channel.
- The `discord.py` package installed in your runtime (not included by default).

Env vars:

- `DISCORD_BOT_TOKEN`: Your bot token.
- `DISCORD_CHANNEL_ID`: The numeric channel ID that accepts the trigger.

Install `discord.py` (if running locally):

```bash
pip install discord.py
```

To include it in the container image, either:

- Add `discord.py` to `app/requirements.txt` and rebuild, or
- Install it at runtime (e.g., via an entrypoint script), understanding this
  may slow startup.

Security note: Treat your bot token like a secret. Do not commit it to source
control; pass it via environment or a secrets manager.

### De-duplication

Identical signals are de-duplicated in the ledger using a unique key on
`(game_id, market, pick, odds)`. Repeated runs that encounter the same price
for the same side will not create duplicate rows.
