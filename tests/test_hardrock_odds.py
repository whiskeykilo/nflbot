"""Tests for :mod:`app.adapters.hardrock_odds`."""

from pathlib import Path
from unittest.mock import Mock, patch

import os
import pytest
import requests

# Ensure the application package is importable when tests are run directly.
import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.adapters.hardrock_odds import fetch_hr_nfl_moneylines


def _mock_response(json_data, status_code=200):
    response = Mock()
    response.json.return_value = json_data
    response.status_code = status_code
    response.raise_for_status.return_value = None
    return response


def test_fetch_hr_nfl_moneylines_parses_response_and_skips_past_games():
    sample = [
        {
            "id": "game-1",
            "commence_time": "2099-09-07T17:00:00Z",
            "home_team": "JAX",
            "teams": ["JAX", "MIA"],
            "bookmakers": [
                {
                    "key": "hardrock",
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [
                                {"name": "JAX", "price": -110},
                                {"name": "MIA", "price": 100},
                            ],
                        }
                    ],
                }
            ],
        },
        {  # This game is in the past and should be filtered out
            "id": "old-game",
            "commence_time": "2000-01-01T00:00:00Z",
            "home_team": "AAA",
            "teams": ["AAA", "BBB"],
            "bookmakers": [],
        },
    ]

    with patch("app.adapters.hardrock_odds.requests.get", return_value=_mock_response(sample)):
        games = fetch_hr_nfl_moneylines()

    assert games == [
        {
            "game_id": "game-1",
            "home": "JAX",
            "away": "MIA",
            "start_utc": "2099-09-07T17:00:00Z",
            "market": "ML",
            "odds_home": -110,
            "odds_away": 100,
        }
    ]


def test_fetch_hr_nfl_moneylines_uses_api_key_and_days_from():
    sample = []
    mock_get = Mock(return_value=_mock_response(sample))

    with patch.dict(os.environ, {"THEODDSAPI": "testkey"}):
        with patch("app.adapters.hardrock_odds.requests.get", mock_get):
            fetch_hr_nfl_moneylines(days_from=2)

    params = mock_get.call_args.kwargs.get("params")
    assert params["apiKey"] == "testkey"
    assert params["daysFrom"] == "2"


def test_fetch_hr_nfl_moneylines_http_error():
    response = _mock_response({}, status_code=500)
    response.raise_for_status.side_effect = requests.HTTPError(response=response)

    with patch("app.adapters.hardrock_odds.requests.get", return_value=response):
        with pytest.raises(RuntimeError):
            fetch_hr_nfl_moneylines()


def test_fetch_hr_nfl_moneylines_timeout():
    with patch("app.adapters.hardrock_odds.requests.get", side_effect=requests.Timeout):
        with pytest.raises(RuntimeError):
            fetch_hr_nfl_moneylines()

