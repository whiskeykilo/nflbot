import os, time, schedule
from datetime import datetime, timezone
from app.adapters.hardrock_odds import fetch_hr_nfl_moneylines
from app.adapters.reference_probs import reference_probs_for
from app.core.ev import expected_value_per_dollar, kelly_fraction
from app.core.store import save_signal
from app.core.notify import push

BANKROLL   = float(os.getenv("BANKROLL","500"))
MIN_EDGE   = float(os.getenv("MIN_EDGE","0.03"))
KELLY_FRAC = float(os.getenv("KELLY_FRACTION","0.5"))
MAX_UNIT   = float(os.getenv("MAX_UNIT","0.02"))
TITLE      = "NFL +EV Signals (Hard Rock)"

def clamp(x, lo, hi): return max(lo, min(hi, x))

def run_once():
    games = fetch_hr_nfl_moneylines()
    ref   = reference_probs_for(games)
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

    if not alerts: return
    alerts.sort(key=lambda a:a["edge"], reverse=True)
    lines=[]
    for a in alerts[:5]:
        save_signal(a)
        lines.append(
          f"{a['event']}  {a['market']}  Pick: **{a['pick']}**  Odds: {a['odds']}  "
          f"True: {a['p_true']:.2f}  Edge: {a['edge']*100:.1f}%  Kelly: {max(0,a['kelly'])*100:.1f}%  "
          f"Stake: ${a['stake']:.2f}  (KO {a['start']})"
        )
    push(TITLE, lines)

def schedule_jobs():
    # NFL-heavy windows: Sunday every 5m; otherwise every 15m
    schedule.every(5).minutes.do(run_once).tag("sun")    # will run daily; it's fine for MVP
    schedule.every(15).minutes.do(run_once).tag("wk")
    run_once()  # fire immediately

if __name__=="__main__":
    schedule_jobs()
    while True:
        schedule.run_pending()
        time.sleep(1)