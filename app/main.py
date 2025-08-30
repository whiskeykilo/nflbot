import os, time, schedule, logging
from typing import List, Dict
from datetime import datetime, timezone, timedelta
from app.adapters.hardrock_odds import fetch_hr_nfl_moneylines
from app.adapters.reference_probs import reference_probs_for
from app.core.errors import OddsApiQuotaError
from app.core.ev import expected_value_per_dollar, kelly_fraction, break_even_prob
from app.core.spreads import map_hr_to_probs as map_probs
from app.core.store import save_signal
from app.core.notify import push

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
_LAST_SIG: str | None = None
_SKIP_NEXT: bool = False

BANKROLL        = float(os.getenv("BANKROLL","500"))
MIN_EDGE        = float(os.getenv("MIN_EDGE","0.01"))
KELLY_FRAC      = float(os.getenv("KELLY_FRACTION","0.5"))
MAX_UNIT        = float(os.getenv("MAX_UNIT","0.02"))
MAX_DAYS_AHEAD  = int(os.getenv("MAX_DAYS_AHEAD", "7"))
TEST_FORCE_OPPS = os.getenv("TEST_FORCE_OPPS", "").strip() not in ("", "0", "false", "False")
TEST_FORCE_COUNT = int(os.getenv("TEST_FORCE_COUNT", "3"))
MAX_INTERP_GAP  = float(os.getenv("MAX_INTERP_GAP", "1.0"))
TITLE      = "NFL +EV Signals on Hard Rock Bet"

# When to run scheduled jobs
SUNDAY_RUN_TIME  = os.getenv("SUNDAY_RUN_TIME", "12:00")
WEEKDAY_RUN_TIME = os.getenv("WEEKDAY_RUN_TIME", "09:00")

def clamp(x, lo, hi): return max(lo, min(hi, x))

def _hr_signature(games: list[dict]) -> str:
    try:
        items = []
        for g in games:
            items.append((g.get("game_id"), g.get("line_home"), g.get("line_away"), g.get("odds_home"), g.get("odds_away")))
        items.sort()
        return str(items)
    except Exception:
        return ""

def run_once():
    try:
        games = fetch_hr_nfl_moneylines(days_from=MAX_DAYS_AHEAD)
    except OddsApiQuotaError as qe:
        logger.error("Odds API quota/rate limit encountered fetching Hard Rock: %s", qe)
        push(TITLE + " - Quota", [
            "The Odds API credits are exhausted or rate-limited.",
            "Skipping this run to preserve budget.",
        ])
        return
    except Exception:
        logger.exception("Failed to fetch Hard Rock NFL spreads")
        push(TITLE + " - Error", ["Failed to fetch Hard Rock NFL spreads; aborting."])
        return
    logger.info("Fetched %d upcoming games from Hard Rock (spreads)", len(games))
    # Change detection: bank next poll if nothing moved
    global _LAST_SIG, _SKIP_NEXT
    sig = _hr_signature(games)
    if _LAST_SIG is not None and sig == _LAST_SIG:
        logger.debug("No movement since last sample; will skip next scheduled poll to bank budget")
        _SKIP_NEXT = True
    _LAST_SIG = sig
    try:
        ref   = reference_probs_for(games)
    except OddsApiQuotaError as qe:
        logger.error("Odds API quota/rate limit encountered fetching Pinnacle refs: %s", qe)
        push(TITLE + " - Quota", [
            "The Odds API credits are exhausted or rate-limited.",
            "Skipping this run to preserve budget.",
        ])
        return
    except Exception:
        logger.exception("Failed to fetch reference probabilities")
        push(TITLE + " - Error", ["Failed to fetch Pinnacle reference probabilities; aborting."])
        return
    # Only consider games that have Pinnacle reference probabilities
    games = [g for g in games if g["game_id"] in ref]
    logger.info("%d games matched to Pinnacle references", len(games))
    def _interp_prob(side_map: Dict[float, float], target: float) -> float | None:
        if target in side_map:
            return side_map[target]
        if not side_map:
            return None
        xs = sorted(side_map.keys())
        # find neighbors
        lo = None
        hi = None
        for x in xs:
            if x <= target:
                lo = x
            if x >= target and hi is None:
                hi = x
        if lo is None or hi is None:
            return None
        if lo == hi:
            return side_map[lo]
        p_lo = side_map[lo]
        p_hi = side_map[hi]
        t = (target - lo) / (hi - lo)
        return p_lo + t * (p_hi - p_lo)

    def _push_prob(side_map: Dict[float, float], line: float) -> float:
        # Pushes occur on whole numbers only; approximate mass between +/- 0.5
        if line is None:
            return 0.0
        if abs(line - round(line)) > 1e-6:
            return 0.0
        p_m = _interp_prob(side_map, line - 0.5)
        p_p = _interp_prob(side_map, line + 0.5)
        if p_m is None or p_p is None:
            return 0.0
        return max(0.0, abs(p_m - p_p))

    # Team abbreviations for cleaner logs/notifications
    TEAM_ABBR = {
        "Arizona Cardinals":"ARI","Atlanta Falcons":"ATL","Baltimore Ravens":"BAL","Buffalo Bills":"BUF",
        "Carolina Panthers":"CAR","Chicago Bears":"CHI","Cincinnati Bengals":"CIN","Cleveland Browns":"CLE",
        "Dallas Cowboys":"DAL","Denver Broncos":"DEN","Detroit Lions":"DET","Green Bay Packers":"GB",
        "Houston Texans":"HOU","Indianapolis Colts":"IND","Jacksonville Jaguars":"JAX","Kansas City Chiefs":"KC",
        "Las Vegas Raiders":"LV","Los Angeles Chargers":"LAC","Los Angeles Rams":"LAR","Miami Dolphins":"MIA",
        "Minnesota Vikings":"MIN","New England Patriots":"NE","New Orleans Saints":"NO","New York Giants":"NYG",
        "New York Jets":"NYJ","Philadelphia Eagles":"PHI","Pittsburgh Steelers":"PIT","San Francisco 49ers":"SF",
        "Seattle Seahawks":"SEA","Tampa Bay Buccaneers":"TB","Tennessee Titans":"TEN","Washington Commanders":"WAS",
    }
    def abbr(name:str)->str: return TEAM_ABBR.get(name, name)

    # Log concise matched games; only include EV when calculable via ladder
    for g in games:
        rid = g["game_id"]
        pr = ref.get(rid, {})
        oh = g.get("odds_home")
        oa = g.get("odds_away")
        lh = g.get("line_home")
        la = g.get("line_away")
        ladder = (pr or {}).get("ladder", {})
        ladder_h = ladder.get("home", {})
        ladder_a = ladder.get("away", {})
        fav_ladder = (pr or {}).get("fav_ladder", {})
        prices = (pr or {}).get("prices", {})
        prices_h = prices.get("home", {})
        prices_a = prices.get("away", {})

        ev_h = ev_a = None
        skip_parts = []
        if oh is not None and lh is not None and fav_ladder:
            mp = map_probs("home", float(lh), fav_ladder, MAX_INTERP_GAP)
            if mp is not None:
                p_win, p_push, _, _meta = mp
                ev_h = expected_value_per_dollar(p_win, oh, p_push)
            else:
                skip_parts.append(f"H {float(lh):+0.1f}")
        if oa is not None and la is not None and fav_ladder:
            mp = map_probs("away", float(la), fav_ladder, MAX_INTERP_GAP)
            if mp is not None:
                p_win, p_push, _, _meta = mp
                ev_a = expected_value_per_dollar(p_win, oa, p_push)
            else:
                skip_parts.append(f"A {float(la):+0.1f}")

        # Choose nearest Pinnacle display prices to HR lines for log context
        def nearest_price(pr_map:Dict[float,int], target:float):
            if not pr_map:
                return None, None
            key = min(pr_map.keys(), key=lambda x: abs(x-target))
            return pr_map.get(key), key

        ph, ph_line = (nearest_price(prices_h, float(lh)) if lh is not None else (None, None))
        pa, pa_line = (nearest_price(prices_a, float(la)) if la is not None else (None, None))

        # Log even if EV not available, but keep concise
        logger.info(
            "%s @ %s - %s | HR: H %s(%s) A %s(%s) | P: H %s(%s) A %s(%s)%s",
            abbr(g.get("away","")), abbr(g.get("home","")), g.get("start_utc"),
            oh, (f"{lh:+.1f}" if lh is not None else "-"),
            oa, (f"{la:+.1f}" if la is not None else "-"),
            (ph if ph is not None else "-"), (f"{ph_line:+.1f}" if ph_line is not None else "-"),
            (pa if pa is not None else "-"), (f"{pa_line:+.1f}" if pa_line is not None else "-"),
            (" | EV " + " ".join(filter(None,[f"H {ev_h*100:+.1f}%" if ev_h is not None else None, f"A {ev_a*100:+.1f}%" if ev_a is not None else None]))) if (ev_h is not None or ev_a is not None) else "",
        )
        if skip_parts:
            logger.debug(
                "EV unavailable (no nearby Pinnacle alt lines <= %.2f): %s @ %s — %s",
                MAX_INTERP_GAP,
                abbr(g.get("away","")),
                abbr(g.get("home","")),
                ", ".join(skip_parts),
            )
    if not games:
        logger.warning("No Pinnacle reference odds matched upcoming games")
        push(TITLE + " - Error", ["No Pinnacle odds found for upcoming games; aborting."])
        return
    alerts=[]
    for g in games:
        rid=g["game_id"]; pr=ref.get(rid)
        if not pr: continue
        fav_ladder = (pr or {}).get("fav_ladder", {})
        evals=[]
        for side in ("home","away"):
            odds=g.get(f"odds_{side}")
            line=g.get(f"line_{side}")
            if odds is None or line is None:
                continue
            if not fav_ladder:
                continue
            mp = map_probs(side, float(line), fav_ladder, MAX_INTERP_GAP)
            if mp is None:
                continue
            p_win, p_push, _, meta = mp
            ev=expected_value_per_dollar(p_win, odds, p_push)
            k=kelly_fraction(p_win, odds, p_push)
            stake=round(BANKROLL*clamp(KELLY_FRAC*max(0,k),0.0,MAX_UNIT),2)
            # Dynamic EV threshold based on mapping risk
            abs_line = abs(float(line))
            near_key = min(abs(abs_line-3.0), abs(abs_line-7.0)) <= 0.5
            thr = max(MIN_EDGE, 0.01)
            if meta.get("whole") or meta.get("interpolated"):
                thr = max(thr, 0.015)
            if meta.get("interpolated") and near_key:
                thr = max(thr, 0.02)
            evals.append((ev,side,odds,p_win,k,stake,line,p_push,thr))
        if not evals:
            continue  # no valid odds for this game
        ev,side,odds,p_true,k,stake,line,p_push,thr=max(evals,key=lambda x:x[0])
        if ev>=thr and stake>=1.0:
            team=g["home"] if side=="home" else g["away"]
            pick=f"{team} {line:+.1f}"
            p_be = break_even_prob(odds, p_push)
            a={"game_id":rid,"market":g["market"],"pick":pick,"odds":odds,
               "p_true":p_true,"p_be":p_be,"p_push":p_push,
               "edge":ev,"kelly":k,"stake":stake,
               "event":f"{g['away']} @ {g['home']}","start":g["start_utc"]}
            alerts.append(a)

    forced = False
    if not alerts and TEST_FORCE_OPPS:
        logger.info("Test mode: forcing %d opportunity/ies for notification", TEST_FORCE_COUNT)
        candidates=[]
        for g in games:
            rid = g["game_id"]; pr = ref.get(rid)
            if not pr:
                continue
            fav_ladder = (pr or {}).get("fav_ladder", {})
            evals=[]
            for side in ("home","away"):
                odds = g.get(f"odds_{side}")
                line = g.get(f"line_{side}")
                if odds is None or line is None:
                    continue
                if not fav_ladder:
                    continue
                mp = map_probs(side, float(line), fav_ladder, MAX_INTERP_GAP)
                if mp is None:
                    continue
                p_win, p_push, _, _meta = mp
                ev = expected_value_per_dollar(p_win, odds, p_push)
                k = kelly_fraction(p_win, odds, p_push)
                stake = round(BANKROLL*clamp(KELLY_FRAC*max(0,k),0.0,MAX_UNIT),2)
                # Ensure we have a visible stake in test mode
                stake = max(1.0, stake)
                p_be = break_even_prob(odds, p_push)
                candidates.append({
                    "game_id": rid,
                    "market": g["market"],
                    "pick": f"{g['home'] if side=='home' else g['away']} {line:+.1f}",
                    "odds": odds,
                    "p_true": p_win,
                    "p_be": p_be,
                    "p_push": p_push,
                    "edge": ev,
                    "kelly": k,
                    "stake": stake,
                    "event": f"{g['away']} @ {g['home']}",
                    "start": g["start_utc"],
                })
        candidates.sort(key=lambda a:a["edge"], reverse=True)
        alerts = candidates[:max(0, TEST_FORCE_COUNT)]
        forced = True

    if not alerts:
        logger.info("No +EV opportunities found above threshold")
        # Allow testing Discord notifications even when no picks are available
        test_notify = os.getenv("TEST_NOTIFY", "").strip() not in ("", "0", "false", "False")
        # If invoked in RUN_ONCE mode, also post a concise empty message to Discord
        run_once_flag = os.getenv("RUN_ONCE", "").strip() not in ("", "0", "false", "False")
        if test_notify:
            push(TITLE + " - Test", ["No +EV opportunities found above threshold."])
        elif run_once_flag:
            push(TITLE, ["No +EV opportunities found above threshold."])
        return
    alerts.sort(key=lambda a:a["edge"], reverse=True)
    lines=[]
    def _fmt_kickoff_local(iso_utc: str) -> str:
        try:
            ts = iso_utc.replace("Z","+00:00")
            dt = datetime.fromisoformat(ts)
            local = dt.astimezone()
            return local.strftime("%a %H:%M")
        except Exception:
            return iso_utc

    for a in alerts[:5]:
        if not forced:
            save_signal(a)
        # Discord: minimal, readable, with emojis
        away, home = a['event'].split(' @ ')
        title_line = f"{abbr(away)} @ {abbr(home)} — {_fmt_kickoff_local(a['start'])} 👊 {a['edge']*100:+.1f}% EV"
        pick_line = f"* Pick: {a['pick']} at {a['odds']}"
        stake_line = f"* Stake: ${a['stake']:.2f}"
        lines.append(f"\n{title_line}\n{pick_line}\n{stake_line}")
    logger.info("Pushing %d alert(s) to Discord%s", len(lines), " (test)" if forced else "")
    push(TITLE + (" - Test" if forced else ""), lines)

def _alloc_times(start: str, end: str, count: int) -> list[str]:
    from datetime import datetime as _dt
    fmt = "%H:%M"
    s = _dt.strptime(start, fmt)
    e = _dt.strptime(end, fmt)
    total = int((e - s).total_seconds() // 60)
    if total <= 0 or count <= 0:
        return []
    if count == 1:
        return [start]
    step = max(1, round(total / (count - 1)))
    times = []
    for i in range(count):
        m = min(total, i * step)
        t = (s.replace()) + timedelta(minutes=int(m))
        times.append(t.strftime(fmt))
    return sorted(list(dict.fromkeys(times)))

def _schedule_at(day: str, times: list[str], tag: str):
    for t in times:
        getattr(schedule.every(), day).at(t).do(_scheduled_job, tag).tag(tag)

def _scheduled_job(tag: str):
    global _SKIP_NEXT
    if _SKIP_NEXT:
        logger.info("Skipping poll (banked) — tag=%s", tag)
        _SKIP_NEXT = False
        return
    run_once()

def schedule_jobs():
    use_opt = os.getenv("USE_OPT_SCHEDULE", "1").strip() not in ("", "0", "false", "False")
    if not use_opt:
        schedule.every().sunday.at(SUNDAY_RUN_TIME).do(run_once).tag("sun")
        schedule.every().day.at(WEEKDAY_RUN_TIME).do(run_once).tag("wk")
        run_once()
        return

    # Scale down in 5-Sunday months (~20%)
    from datetime import date
    import calendar
    today = date.today()
    _, days_in_month = calendar.monthrange(today.year, today.month)
    sundays = sum(1 for d in range(1, days_in_month + 1) if date(today.year, today.month, d).weekday() == 6)
    scale = 0.8 if sundays >= 5 else 1.0
    def sc(n: int) -> int:
        return max(1, int(round(n * scale)))

    # Sunday 1pm slate
    _schedule_at("sunday", _alloc_times("11:30", "11:45", sc(8)), "sun_1p_inactives")
    _schedule_at("sunday", _alloc_times("12:30", "12:59", sc(12)), "sun_1p_final")

    # Sunday 4:25pm slate
    _schedule_at("sunday", _alloc_times("14:55", "15:10", sc(6)), "sun_425_inactives")
    _schedule_at("sunday", _alloc_times("16:05", "16:25", sc(4)), "sun_425_final")

    # SNF (approx 20:20): T−75 to T−10
    _schedule_at("sunday", _alloc_times("19:05", "20:10", sc(6)), "snf")

    # MNF (approx 20:15)
    _schedule_at("monday", _alloc_times("19:00", "20:05", sc(6)), "mnf")

    # TNF (approx 20:15)
    _schedule_at("thursday", _alloc_times("19:00", "20:05", sc(6)), "tnf")

    # Sunday night openers for next week
    _schedule_at("sunday", _alloc_times("20:00", "23:00", sc(6)), "sun_openers")

    # Friday game-status window
    _schedule_at("friday", _alloc_times("15:30", "18:30", sc(4)), "fri_status")

    # Saturday limits rise
    _schedule_at("saturday", _alloc_times("18:00", "23:30", sc(4)), "sat_limits")

    logger.info("Optimized poll schedule installed (scale=%.2f). First run firing now.", scale)
    run_once()
    # TODO(one-shot): Consider skipping immediate run when in strict schedule-only mode

if __name__=="__main__":
    # Simple startup: run once or start scheduler (no Discord listener)
    if os.getenv("RUN_ONCE", "").strip() not in ("", "0", "false", "False"):
        run_once()
    else:
        schedule_jobs()
        while True:
            schedule.run_pending()
            time.sleep(1)
