import os, time, schedule, logging
from typing import List, Dict
import threading, asyncio
from datetime import datetime, timezone
from app.adapters.hardrock_odds import fetch_hr_nfl_moneylines
from app.adapters.reference_probs import reference_probs_for
from app.core.ev import expected_value_per_dollar, kelly_fraction
from app.core.store import save_signal
from app.core.notify import push

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

BANKROLL   = float(os.getenv("BANKROLL","500"))
MIN_EDGE   = float(os.getenv("MIN_EDGE","0.03"))
KELLY_FRAC = float(os.getenv("KELLY_FRACTION","0.5"))
MAX_UNIT   = float(os.getenv("MAX_UNIT","0.02"))
TITLE      = "NFL +EV Signals (Hard Rock)"

# When to run scheduled jobs
SUNDAY_RUN_TIME  = os.getenv("SUNDAY_RUN_TIME", "12:00")
WEEKDAY_RUN_TIME = os.getenv("WEEKDAY_RUN_TIME", "09:00")

def clamp(x, lo, hi): return max(lo, min(hi, x))

def run_once():
    try:
        games = fetch_hr_nfl_moneylines()
    except Exception:
        logger.exception("Failed to fetch Hard Rock NFL moneylines")
        push(TITLE + " - Error", ["Failed to fetch Hard Rock NFL moneylines; aborting."])
        return
    logger.info("Fetched %d upcoming games from Hard Rock", len(games))
    try:
        ref   = reference_probs_for(games)
    except Exception:
        logger.exception("Failed to fetch reference probabilities")
        push(TITLE + " - Error", ["Failed to fetch Pinnacle reference probabilities; aborting."])
        return
    # Only consider games that have Pinnacle reference probabilities
    games = [g for g in games if g["game_id"] in ref]
    logger.info("%d games matched to Pinnacle references", len(games))
    if not games:
        logger.warning("No Pinnacle reference odds matched upcoming games")
        push(TITLE + " - Error", ["No Pinnacle odds found for upcoming games; aborting."])
        return
    alerts=[]
    for g in games:
        rid=g["game_id"]; pr=ref.get(rid)
        if not pr: continue
        evals=[]
        for side in ("home","away"):
            odds=g[f"odds_{side}"]; p_true=pr[f"p_{side}"]
            ev=expected_value_per_dollar(p_true,odds)
            k=kelly_fraction(p_true,odds)
            stake=round(BANKROLL*clamp(KELLY_FRAC*max(0,k),0.0,MAX_UNIT),2)
            evals.append((ev,side,odds,p_true,k,stake))
        ev,side,odds,p_true,k,stake=max(evals,key=lambda x:x[0])
        if ev>=MIN_EDGE and stake>=1.0:
            pick=g["home"] if side=="home" else g["away"]
            a={"game_id":rid,"market":g["market"],"pick":pick,"odds":odds,
               "p_true":p_true,"edge":ev,"kelly":k,"stake":stake,
               "event":f"{g['away']} @ {g['home']}","start":g["start_utc"]}
            alerts.append(a)

    if not alerts:
        logger.info("No +EV opportunities found above threshold")
        return
    alerts.sort(key=lambda a:a["edge"], reverse=True)
    lines=[]
    for a in alerts[:5]:
        save_signal(a)
        lines.append(
          f"{a['event']}  {a['market']}  Pick: **{a['pick']}**  Odds: {a['odds']}  "
          f"True: {a['p_true']:.2f}  Edge: {a['edge']*100:.1f}%  Kelly: {max(0,a['kelly'])*100:.1f}%  "
          f"Stake: ${a['stake']:.2f}  (KO {a['start']})"
        )
    logger.info("Pushing %d alert(s) to Discord", len(lines))
    push(TITLE, lines)

def schedule_jobs():
    schedule.every().sunday.at(SUNDAY_RUN_TIME).do(run_once).tag("sun")
    schedule.every().day.at(WEEKDAY_RUN_TIME).do(run_once).tag("wk")
    run_once()  # fire immediately
    # TODO(one-shot): Consider skipping immediate run when in strict schedule-only mode

if __name__=="__main__":
    # TODO(logs): Emit startup config (excluding secrets) for clarity
    # Optionally start Discord listener for manual trigger
    def _maybe_start_discord_listener():
        token = os.getenv("DISCORD_BOT_TOKEN")
        channel_id = os.getenv("DISCORD_CHANNEL_ID")
        if not token or not channel_id:
            return
        try:
            import discord  # type: ignore
        except Exception:
            logger.warning("discord.py not installed; manual trigger disabled")
            return

        async def _run_bot():
            intents = discord.Intents.default()
            intents.message_content = True

            class Bot(discord.Client):
                async def on_ready(self):
                    logger.info("Discord bot ready as %s", self.user)

                async def on_message(self, message):
                    try:
                        if str(message.channel.id) != str(channel_id):
                            return
                        if getattr(message.author, "bot", False):
                            return
                        content = (message.content or "").strip().lower()
                        if content in {"run", "!run", "/run"}:
                            await message.add_reaction("✅")
                            await asyncio.to_thread(run_once)
                    except Exception:
                        logger.exception("Error handling Discord message")

            client = Bot(intents=intents)
            await client.start(token)

        def _thread_target():
            try:
                asyncio.run(_run_bot())
            except Exception:
                logger.exception("Discord listener stopped unexpectedly")

        t = threading.Thread(target=_thread_target, name="discord-listener", daemon=True)
        t.start()

    if os.getenv("RUN_ONCE", "").strip() not in ("", "0", "false", "False"):
        run_once()
    else:
        _maybe_start_discord_listener()
        schedule_jobs()
        while True:
            schedule.run_pending()
            time.sleep(1)
