"""HTTP client for fetching NFL moneyline odds from Hard Rock.

The Hard Rock sportsbook does not provide an officially documented public
API, but their odds are available through third party aggregators such as
`the-odds-api.com`.  This module implements a thin wrapper around such an
endpoint and converts the response into a simplified dictionary structure
used by the rest of the project.

Only the fields required by :mod:`app.main` are exposed:

``game_id``
    Identifier for the event.
``home`` / ``away``
    Team abbreviations.
``start_utc``
    Kick off time as an ISO8601 string in UTC.
``market``
    Market identifier – we only fetch moneyline (ML) markets.
``odds_home`` / ``odds_away``
    American odds for each side of the moneyline.

The function performs basic error handling and will raise ``RuntimeError``
with a meaningful message if the request fails or returns malformed JSON.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import List, Dict

import requests
from dateutil import parser as dateparser

# In production you would likely pull an API key from the environment and use
# the official Hard Rock endpoint. For the purposes of this repository we use
# The Odds API which aggregates odds for many books, including Hard Rock. The
# API key is optional and supplied via the ``THEODDSAPI`` environment variable.
API_URL = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds"

# Static query parameters for the Odds API. ``daysFrom`` and the optional
# ``apiKey`` are added at request time.
DEFAULT_PARAMS = {
    "regions": "us",
    "markets": "h2h",
    "bookmakers": "hardrock",
    "oddsFormat": "american",
    "dateFormat": "iso",
}


def _to_utc(dt_str: str) -> datetime:
    """Parse a datetime string and return an aware UTC ``datetime``."""

    dt = dateparser.isoparse(dt_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def fetch_hr_nfl_moneylines(timeout: float = 10.0, days_from: int = 1) -> List[Dict]:
    """Retrieve live NFL moneyline odds from Hard Rock.

    Parameters
    ----------
    timeout:
        Maximum time in seconds to wait for the HTTP request.

    Returns
    -------
    list[dict]
        Simplified list of game dictionaries as described above.

    Raises
    ------
    RuntimeError
        If the HTTP request fails, times out or returns malformed JSON.
    """

    params = DEFAULT_PARAMS.copy()
    params["daysFrom"] = str(days_from)

    api_key = os.getenv("THEODDSAPI")
    if api_key:
        params["apiKey"] = api_key

    try:
        resp = requests.get(API_URL, params=params, timeout=timeout)
        resp.raise_for_status()
    except requests.Timeout as exc:
        raise RuntimeError("Timeout fetching Hard Rock odds") from exc
    except requests.HTTPError as exc:  # pragma: no cover - branch tested
        status = exc.response.status_code if exc.response else "unknown"
        raise RuntimeError(f"HTTP {status} fetching Hard Rock odds") from exc
    except requests.RequestException as exc:  # pragma: no cover - branch tested
        raise RuntimeError(f"Error fetching Hard Rock odds: {exc}") from exc

    try:
        events = resp.json()
    except ValueError as exc:
        raise RuntimeError("Invalid JSON from Hard Rock odds endpoint") from exc

    now = datetime.now(timezone.utc)
    games: List[Dict] = []

    for event in events:
        commence = event.get("commence_time")
        if not commence:
            continue
        start_dt = _to_utc(commence)
        if start_dt < now:
            continue  # ignore games that have already started

        game_id = event.get("id")
        home_team = event.get("home_team")
        teams = event.get("teams", [])
        away_team = next((t for t in teams if t != home_team), None)

        odds_home = odds_away = None
        bookmakers = event.get("bookmakers", [])
        if bookmakers:
            markets = bookmakers[0].get("markets", [])
            market = next((m for m in markets if m.get("key") == "h2h"), None)
            if market:
                outcomes = {o["name"]: o["price"] for o in market.get("outcomes", [])}
                odds_home = outcomes.get(home_team)
                odds_away = outcomes.get(away_team)

        games.append(
            {
                "game_id": game_id,
                "home": home_team,
                "away": away_team,
                "start_utc": start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "market": "ML",
                "odds_home": odds_home,
                "odds_away": odds_away,
            }
        )

    games.sort(key=lambda g: g["start_utc"])  # deterministic ordering for cron jobs
    return games
