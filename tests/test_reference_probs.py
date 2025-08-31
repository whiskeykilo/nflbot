import sys
from pathlib import Path

import pytest
import requests

# Ensure repo root on path for package imports
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.adapters.reference_probs import reference_probs_for


class DummyResponse:
    def __init__(self, data, status_code: int = 200):
        self._data = data
        self.status_code = status_code
        self.headers = {}

    def raise_for_status(self):
        if self.status_code != 200:
            raise requests.HTTPError(self.status_code)

    def json(self):
        return self._data


def test_reference_probs_from_external(monkeypatch):
    games = [
        {"game_id": "G1", "home": "H", "away": "A"}
    ]

    external = [
        {
            "id": "G1",
            "home_team": "H",
            "away_team": "A",
            "bookmakers": [
                {
                    "key": "pinnacle",
                    "markets": [
                        {
                            "key": "spreads",
                            "outcomes": [
                                {"name": "H", "price": -120, "point": -2.5},
                                {"name": "A", "price": 110, "point": 2.5},
                            ],
                        },
                        {
                            "key": "h2h",
                            "outcomes": [
                                {"name": "H", "price": -150},
                                {"name": "A", "price": 130},
                            ],
                        },
                    ],
                }
            ],
        }
    ]

    def fake_get(url, params=None, timeout=0):
        return DummyResponse(external)

    monkeypatch.setattr(requests, "get", fake_get)

    probs = reference_probs_for(games)

    assert "G1" in probs
    # At -2.5 the de-vig fair probs should match the ratio of quoted probs
    assert pytest.approx(probs["G1"]["p_home"], 0.0001) == 0.5338983050847457
    assert pytest.approx(probs["G1"]["p_away"], 0.0001) == 0.4661016949152542
    # Moneyline probabilities
    assert pytest.approx(probs["G1"]["ml"]["home"], 0.0001) == 0.5798319327731092
    assert pytest.approx(probs["G1"]["ml"]["away"], 0.0001) == 0.42016806722689076


def test_reference_probs_raises_on_external_failure(monkeypatch):
    games = [
        {"game_id": "G1", "home": "H", "away": "A"}
    ]

    def fake_get(url, params=None, timeout=0):
        raise requests.RequestException

    monkeypatch.setattr(requests, "get", fake_get)

    with pytest.raises(RuntimeError):
        reference_probs_for(games)
