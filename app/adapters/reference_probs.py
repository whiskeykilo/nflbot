"""Reference probabilities from a sharp source (Pinnacle via The Odds API).

This module pulls market-implied probabilities from Pinnacle spread (ATS) and
moneyline odds and then removes the vig to obtain "true" probabilities. Fallback
to local odds is intentionally disabled: if Pinnacle data cannot be retrieved,
the caller should abort the run.

Requires an API key in the environment variable ``THEODDSAPI``. Missing keys or
request failures raise ``RuntimeError`` so the caller can notify and stop.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from app.core.errors import OddsApiQuotaError
import logging

from app.core.ev import american_to_implied_prob

def build_pinnacle_fair_ladder(event: dict) -> Dict[float, float] | None:
    """Build a favorite-centric de‑vig probability ladder from a Pinnacle event.

    Returns a mapping from favorite spreads (negative numbers) to the fair
    probability that the favorite covers that spread.
    """
    bm = None
    for b in event.get("bookmakers", []):
        if b.get("key") == BOOKMAKER:
            bm = b
            break
    if not bm:
        return None
    ladder: Dict[float, float] = {}
    for m in bm.get("markets", []):
        if m.get("key") != "spreads":
            continue
        outs = m.get("outcomes", [])
        # Extract points and prices
        fav_point: Optional[float] = None
        fav_price: Optional[int] = None
        dog_price: Optional[int] = None
        for o in outs:
            name = o.get("name")
            point = o.get("point")
            price = _to_int(o.get("price"))
            if point is None or price is None:
                continue
            try:
                p = float(point)
            except Exception:
                continue
            # Favorite has negative point at that market
            if p < 0:
                fav_point = p
                fav_price = price
            else:
                dog_price = price
        if fav_point is None or fav_price is None or dog_price is None:
            continue
        q_fav = american_to_implied_prob(fav_price)
        q_dog = american_to_implied_prob(dog_price)
        s = q_fav + q_dog
        if s <= 0:
            continue
        p_fav = q_fav / s
        ladder[fav_point] = p_fav
    return ladder or None

def _to_int(x: Optional[int]) -> Optional[int]:
    try:
        return int(x) if x is not None else None
    except Exception:
        return None


ODDS_API_URL = (
    "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds"
)
BOOKMAKER = "pinnacle"
PINNACLE_TIMEOUT: Tuple[float, float] = (3.0, 12.0)


def _build_retry_session() -> requests.Session:
    session = requests.Session()
    retries = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=0.5,
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _devig(p1: float, p2: float) -> tuple[float, float]:
    s = p1 + p2
    return (p1 / s, p2 / s) if s > 0 else (0.5, 0.5)


def _from_external(game_id: str, event: dict) -> dict | None:
    """Extract vig-free probabilities and spread ladders for a single event.

    The event structure mirrors that returned from The Odds API.  Returns a
    dict with ``p_home`` and ``p_away`` if successful, otherwise ``None``.
    """

    try:
        bm = None
        for b in event.get("bookmakers", []):
            if b.get("key") == BOOKMAKER:
                bm = b
                break
        if not bm:
            return None
        fav_ladder = build_pinnacle_fair_ladder(event) or {}
        ladder_home: Dict[float, float] = {}
        ladder_away: Dict[float, float] = {}
        prices_home: Dict[float, int] = {}
        prices_away: Dict[float, int] = {}
        ml_home_prob: Optional[float] = None
        ml_away_prob: Optional[float] = None
        ml_price_home: Optional[int] = None
        ml_price_away: Optional[int] = None
        # Some APIs provide multiple "spreads" entries for alternate lines
        for m in bm.get("markets", []):
            key = m.get("key")
            outs = m.get("outcomes", [])
            if key == "spreads":
                price_home: Optional[int] = None
                price_away: Optional[int] = None
                line_home: Optional[float] = None
                line_away: Optional[float] = None
                for o in outs:
                    if o.get("name") == event.get("home_team"):
                        price_home = _to_int(o.get("price"))
                        line_home = o.get("point")
                    elif o.get("name") == event.get("away_team"):
                        price_away = _to_int(o.get("price"))
                        line_away = o.get("point")
                if price_home is None or price_away is None:
                    continue
                p_h = american_to_implied_prob(price_home)
                p_a = american_to_implied_prob(price_away)
                p_h, p_a = _devig(p_h, p_a)
                if line_home is not None:
                    try:
                        ladder_home[float(line_home)] = p_h
                        if price_home is not None:
                            prices_home[float(line_home)] = int(price_home)
                    except Exception:
                        pass
                if line_away is not None:
                    try:
                        ladder_away[float(line_away)] = p_a
                        if price_away is not None:
                            prices_away[float(line_away)] = int(price_away)
                    except Exception:
                        pass
            elif key == "h2h":
                price_home = price_away = None
                for o in outs:
                    if o.get("name") == event.get("home_team"):
                        price_home = _to_int(o.get("price"))
                    elif o.get("name") == event.get("away_team"):
                        price_away = _to_int(o.get("price"))
                if price_home is not None and price_away is not None:
                    p_h = american_to_implied_prob(price_home)
                    p_a = american_to_implied_prob(price_away)
                    p_h, p_a = _devig(p_h, p_a)
                    ml_home_prob = p_h
                    ml_away_prob = p_a
                    ml_price_home = price_home
                    ml_price_away = price_away
        # Pick a representative line near 0 for convenience in logs if spreads exist
        result = {
            "ladder": {"home": ladder_home, "away": ladder_away},
            "prices": {"home": prices_home, "away": prices_away},
            "fav_ladder": fav_ladder,
        }
        if ladder_home and ladder_away:
            def _closest_line(d: Dict[float, float]) -> float:
                return sorted(d.keys(), key=lambda x: abs(x))[0]
            ch = _closest_line(ladder_home)
            ca = _closest_line(ladder_away)
            result.update({
                "p_home": ladder_home[ch],
                "p_away": ladder_away[ca],
                "line_home": ch,
                "line_away": ca,
            })
        if ml_home_prob is not None and ml_away_prob is not None:
            result["ml"] = {
                "home": ml_home_prob,
                "away": ml_away_prob,
                "prices": {"home": ml_price_home, "away": ml_price_away},
            }
        if not result.get("ladder")["home"] and "ml" not in result:
            return None
        return result
    except Exception:
        return None


def reference_probs_for(games: List[Dict]) -> Dict[str, Dict[str, float]]:
    """Return vig-removed reference probabilities for each game.

    Parameters
    ----------
    games:
        Iterable of game dictionaries containing at minimum ``game_id``.
    """

    out: Dict[str, Dict[str, float]] = {}

    data = None
    params = {
        "markets": "spreads,h2h",
        "regions": "us",
        "bookmakers": BOOKMAKER,
        "oddsFormat": "american",
        "dateFormat": "iso",
        # The Odds API may include alternate lines under the same key; no extra flag here.
    }
    api_key = os.getenv("THEODDSAPI")
    if api_key:
        params["apiKey"] = api_key
    # Require external reference prices; raise on failure so caller can abort
    try:
        with _build_retry_session() as session:
            resp = session.get(ODDS_API_URL, params=params, timeout=PINNACLE_TIMEOUT)
        # Quota/rate limit detection
        if resp.status_code in (402, 429):
            raise OddsApiQuotaError(f"The Odds API quota/rate limit hit (HTTP {resp.status_code})")
        # Warn if about to exhaust
        remaining = resp.headers.get("x-requests-remaining") or resp.headers.get("X-Requests-Remaining")
        try:
            if remaining is not None and str(remaining).isdigit() and int(remaining) <= 0:
                logging.getLogger(__name__).warning("The Odds API requests remaining is 0; further calls may fail")
        except Exception:
            pass
        resp.raise_for_status()
        data = resp.json()
    except OddsApiQuotaError:
        raise
    except Exception as exc:
        # Bubble up quota-related errors from body if present
        msg = str(exc)
        if any(k in msg.lower() for k in ("no_active_plan", "insufficient", "quota", "rate limit")):
            raise OddsApiQuotaError("The Odds API quota/rate limit hit") from exc
        raise RuntimeError(f"Failed to fetch Pinnacle reference probabilities: {exc}") from exc

    index = {e.get("id"): e for e in data or []}

    for g in games:
        rid = g["game_id"]
        ref = None
        if rid in index:
            ref = _from_external(rid, index[rid])

        if ref:
            out[rid] = ref

    return out
