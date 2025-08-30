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
