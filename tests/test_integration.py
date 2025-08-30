from pathlib import Path
import sqlite3

import sys

import pytest

# Ensure repo root on path for package imports
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core import store
from app import main as app_main


def test_integration_run_once_pushes_and_persists(monkeypatch, tmp_path):
    # Point ledger at a temp DB
    store.DB_PATH = str(tmp_path / "signals.sqlite")

    # Mock Hard Rock odds: one future game
    games = [
        {
            "game_id": "G1",
            "home": "HOM",
            "away": "AWY",
            "start_utc": "2099-09-07T17:00:00Z",
            "market": "ML",
            "odds_home": 150,
            "odds_away": -160,
        }
    ]

    monkeypatch.setattr(
        app_main, "fetch_hr_nfl_moneylines", lambda: games
    )

    # Mock Pinnacle reference probabilities (vig-removed)
    monkeypatch.setattr(
        app_main, "reference_probs_for", lambda gs: {"G1": {"p_home": 0.45, "p_away": 0.55}}
    )

    pushed = {}

    def fake_push(title, lines):
        pushed["title"] = title
        pushed["lines"] = lines

    monkeypatch.setattr(app_main, "push", fake_push)

    # Configure bankroll/thresholds to ensure inclusion
    monkeypatch.setattr(app_main, "BANKROLL", 100.0)
    monkeypatch.setattr(app_main, "MIN_EDGE", 0.03)
    monkeypatch.setattr(app_main, "KELLY_FRAC", 0.5)
    monkeypatch.setattr(app_main, "MAX_UNIT", 0.02)

    app_main.run_once()

    # Assert Discord push was called with one alert line
    assert pushed.get("title") == "NFL +EV Signals (Hard Rock)"
    assert isinstance(pushed.get("lines"), list) and len(pushed["lines"]) == 1
    line = pushed["lines"][0]
    # Basic content checks
    assert "AWY @ HOM" in line
    assert "Pick: **HOM**" in line
    assert "Odds: 150" in line
    assert "True: 0.45" in line
    assert "Edge: 12.5%" in line
    assert "Kelly: 8.3%" in line
    assert "Stake: $2.00" in line

    # Assert row persisted once
    with sqlite3.connect(store.DB_PATH) as conn:
        rows = conn.execute("SELECT game_id, pick, odds, stake FROM signals").fetchall()
    assert rows == [("G1", "HOM", 150, 2.0)]
