"""Reference probabilities from a sharp source (Pinnacle via The Odds API).

This module attempts to pull market-implied probabilities from a consensus
source.  We query The Odds API for Pinnacle moneyline odds and then remove the
vig to obtain a "true" probability for each side.  If the external data source
is unavailable or does not contain a given game, we fall back to deriving the
probabilities directly from the odds supplied with each game.

The external request requires an API key in the environment variable
``THEODDSAPI``.  Missing keys, network issues or unexpected payloads all
trigger the local fallback behaviour.
"""

from __future__ import annotations

import os
from typing import Dict, List

import requests

from app.core.ev import american_to_implied_prob


ODDS_API_URL = (
    "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds"
)
BOOKMAKER = "pinnacle"


def _devig(p1: float, p2: float) -> tuple[float, float]:
    s = p1 + p2
    return (p1 / s, p2 / s) if s > 0 else (0.5, 0.5)


def _from_external(game_id: str, event: dict) -> dict | None:
    """Extract vig-free probabilities for a single event.

    The event structure mirrors that returned from The Odds API.  Returns a
    dict with ``p_home`` and ``p_away`` if successful, otherwise ``None``.
    """

    try:
        market = None
        for bm in event.get("bookmakers", []):
            if bm.get("key") == BOOKMAKER:
                for m in bm.get("markets", []):
                    if m.get("key") == "h2h":
                        market = m
                        break
            if market:
                break
        if not market:
            return None
        outcomes = market.get("outcomes", [])
        price_home = None
        price_away = None
        for o in outcomes:
            if o.get("name") == event.get("home_team"):
                price_home = o.get("price")
            elif o.get("name") == event.get("away_team"):
                price_away = o.get("price")
        if price_home is None or price_away is None:
            return None
        p_h = american_to_implied_prob(price_home)
        p_a = american_to_implied_prob(price_away)
        p_h, p_a = _devig(p_h, p_a)
        return {"p_home": p_h, "p_away": p_a}
    except Exception:
        return None


def reference_probs_for(games: List[Dict]) -> Dict[str, Dict[str, float]]:
    """Return vig-removed reference probabilities for each game.

    Parameters
    ----------
    games:
        Iterable of game dictionaries containing at minimum ``game_id``,
        ``odds_home`` and ``odds_away``.
    """

    out: Dict[str, Dict[str, float]] = {}

    data = None
    params = {
        "markets": "h2h",
        "regions": "us",
        "bookmakers": BOOKMAKER,
    }
    api_key = os.getenv("THEODDSAPI")
    if api_key:
        params["apiKey"] = api_key

    try:  # Best effort to fetch external data
        resp = requests.get(ODDS_API_URL, params=params, timeout=3)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        data = None

    index = {e.get("id"): e for e in data or []}

    for g in games:
        rid = g["game_id"]
        ref = None
        if rid in index:
            ref = _from_external(rid, index[rid])

        if not ref:  # fall back to odds bundled with the game
            p_h = american_to_implied_prob(g["odds_home"])
            p_a = american_to_implied_prob(g["odds_away"])
            p_h, p_a = _devig(p_h, p_a)
            ref = {"p_home": p_h, "p_away": p_a}

        out[rid] = ref

    return out

