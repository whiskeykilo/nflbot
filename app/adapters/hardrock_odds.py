"""HTTP client for fetching NFL spread and moneyline odds from Hard Rock.

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
``odds_home`` / ``odds_away``
    American odds for each side against the spread.
``line_home`` / ``line_away``
    The spread (handicap) in points for each team.
``ml_home`` / ``ml_away``
    American moneyline odds for each team.

The function performs basic error handling and will raise ``RuntimeError``
with a meaningful message if the request fails or returns malformed JSON.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
import logging
from typing import List, Dict, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dateutil import parser as dateparser
from app.core.errors import OddsApiQuotaError

# In production you would likely pull an API key from the environment and use
# the official Hard Rock endpoint. For the purposes of this repository we use
# The Odds API which aggregates odds for many books, including Hard Rock. The
# API key is optional and supplied via the ``THEODDSAPI`` environment variable.
API_URL = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds"

# Static query parameters for the Odds API. ``daysFrom`` and the optional
# ``apiKey`` are added at request time.
DEFAULT_PARAMS = {
    "regions": "us",
    "markets": "spreads,h2h",
    "bookmakers": "hardrockbet,hardrock",
    "oddsFormat": "american",
    "dateFormat": "iso",
}

BM_KEYS = ("hardrockbet", "hardrock")

def _to_int(x: Optional[int]) -> Optional[int]:
    try:
        return int(x) if x is not None else None
    except Exception:
        return None


def _to_utc(dt_str: str) -> datetime:
    """Parse a datetime string and return an aware UTC ``datetime``."""

    dt = dateparser.isoparse(dt_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _looks_like_quota(resp: requests.Response, body_text: str) -> bool:
    """Best-effort detection of quota exhaustion style responses."""

    lowered = body_text.lower()
    if any(token in lowered for token in ("quota", "rate limit", "plan", "subscription", "insufficient")):
        return True
    remaining = resp.headers.get("x-requests-remaining") or resp.headers.get("X-Requests-Remaining")
    if remaining is not None:
        try:
            if int(remaining) <= 0:
                return True
        except ValueError:
            pass
    return False


def _check_quota_or_raise(resp: requests.Response) -> None:
    # Raise specific error on common quota/rate limit statuses
    if resp.status_code in (402, 429):
        raise OddsApiQuotaError(f"The Odds API quota/rate limit hit (HTTP {resp.status_code})")
    if resp.status_code == 401:
        body_text = ""
        try:
            data = resp.json()
            if isinstance(data, dict):
                body_text = " ".join(str(v) for v in data.values() if v is not None)
            else:
                body_text = str(data)
        except ValueError:
            body_text = getattr(resp, "text", "") or ""
        if _looks_like_quota(resp, body_text):
            raise OddsApiQuotaError("The Odds API quota/rate limit hit (HTTP 401)")
    # On success, emit warning if headers indicate zero remaining
    try:
        remaining = resp.headers.get("x-requests-remaining") or resp.headers.get("X-Requests-Remaining")
        if remaining is not None and str(remaining).isdigit() and int(remaining) <= 0:
            logging.getLogger(__name__).warning("The Odds API requests remaining is 0; further calls may fail")
    except Exception:
        pass


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


def fetch_hr_nfl_moneylines(
    timeout: Tuple[float, float] = (3.0, 15.0),
    days_from: int = 7,
) -> List[Dict]:
    """Retrieve live NFL spread lines from Hard Rock.

    Parameters
    ----------
    timeout:
        Tuple of (connect timeout, read timeout) in seconds.

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
        with _build_retry_session() as session:
            resp = session.get(API_URL, params=params, timeout=timeout)
        _check_quota_or_raise(resp)
        resp.raise_for_status()
    except requests.Timeout as exc:
        raise RuntimeError("Timeout fetching Hard Rock odds") from exc
    except requests.HTTPError as exc:  # pragma: no cover - branch tested
        status = exc.response.status_code if exc.response else "unknown"
        # Surface quota errors distinctly
        if isinstance(status, int) and status in (402, 429):
            raise OddsApiQuotaError(f"The Odds API quota/rate limit hit (HTTP {status})") from exc
        raise RuntimeError(f"HTTP {status} fetching Hard Rock odds") from exc
    except requests.RequestException as exc:  # pragma: no cover - branch tested
        # Try to detect quota error from body text
        msg = str(exc)
        if any(k in msg.lower() for k in ("no_active_plan", "insufficient", "quota", "rate limit")):
            raise OddsApiQuotaError("The Odds API quota/rate limit hit") from exc
        raise RuntimeError(f"Error fetching Hard Rock odds: {exc}") from exc

    try:
        events = resp.json()
    except ValueError as exc:
        raise RuntimeError("Invalid JSON from Hard Rock odds endpoint") from exc

    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=max(1, int(days_from)))
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
        # Prefer explicit away_team if provided by API, otherwise infer from "teams"
        away_team = event.get("away_team")
        if not away_team:
            teams = event.get("teams", [])
            away_team = next((t for t in teams if t != home_team), None)

        # Ignore games outside the cutoff window (focus on current week)
        if start_dt > cutoff:
            continue

        odds_home = odds_away = None
        line_home = line_away = None
        ml_home = ml_away = None
        bookmakers = event.get("bookmakers", [])
        if bookmakers:
            bm = None
            for key in BM_KEYS:
                bm = next((b for b in bookmakers if b.get("key") == key), None)
                if bm:
                    break
            if bm is None:
                bm = bookmakers[0]
            markets = bm.get("markets", [])
            market_spread = next((m for m in markets if m.get("key") == "spreads"), None)
            if market_spread:
                outcomes = {o.get("name"): o for o in market_spread.get("outcomes", [])}
                if home_team is not None and home_team in outcomes:
                    oh = outcomes[home_team]
                    odds_home = _to_int(oh.get("price"))
                    line_home = oh.get("point")
                if away_team is not None and away_team in outcomes:
                    oa = outcomes[away_team]
                    odds_away = _to_int(oa.get("price"))
                    line_away = oa.get("point")
            market_ml = next((m for m in markets if m.get("key") == "h2h"), None)
            if market_ml:
                outcomes = {o.get("name"): o for o in market_ml.get("outcomes", [])}
                if home_team is not None and home_team in outcomes:
                    ml_home = _to_int(outcomes[home_team].get("price"))
                if away_team is not None and away_team in outcomes:
                    ml_away = _to_int(outcomes[away_team].get("price"))

        games.append(
            {
                "game_id": game_id,
                "home": home_team,
                "away": away_team,
                "start_utc": start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "market": "BOTH",
                "odds_home": odds_home,
                "odds_away": odds_away,
                "line_home": line_home,
                "line_away": line_away,
                "ml_home": ml_home,
                "ml_away": ml_away,
            }
        )

    games.sort(key=lambda g: g["start_utc"])  # deterministic ordering for cron jobs
    return games
