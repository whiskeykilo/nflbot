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
            "market": "SPREAD",
            "odds_home": -105,
            "odds_away": -115,
            "line_home": -2.5,
            "line_away": 2.5,
        }
    ]

    monkeypatch.setattr(app_main, "fetch_hr_nfl_moneylines", lambda days_from=7: games)

    # Mock Pinnacle favorite ladder with fair p_fav_cover at -2.5
    ref = {
        "G1": {
            "fav_ladder": { -2.5: 0.53 },
            "ladder": {"home": {-2.5: 0.53}, "away": {2.5: 0.47}},
            "prices": {"home": {-2.5: -110}, "away": {2.5: -110}},
        }
    }
    monkeypatch.setattr(app_main, "reference_probs_for", lambda gs: ref)

    pushed = {}

    def fake_push(title, lines):
        pushed["title"] = title
        pushed["lines"] = lines

    monkeypatch.setattr(app_main, "push", fake_push)

    # Configure bankroll/thresholds to ensure inclusion
    monkeypatch.setattr(app_main, "BANKROLL", 100.0)
    monkeypatch.setattr(app_main, "MIN_EDGE", 0.01)
    monkeypatch.setattr(app_main, "KELLY_FRAC", 0.5)
    monkeypatch.setattr(app_main, "MAX_UNIT", 0.02)
    monkeypatch.setattr(app_main, "MAX_INTERP_GAP", 2.0)

    app_main.run_once()

    # Assert Discord push was called with one alert block
    assert pushed.get("title").startswith("NFL +EV Signals")
    assert isinstance(pushed.get("lines"), list) and len(pushed["lines"]) == 1
    block = pushed["lines"][0]
    # Basic content checks for new format
    assert "AWY @ HOM" in block
    assert "* Pick:" in block and "HOM -2.5" in block
    assert "* Stake:" in block

    # Assert row persisted once
    with sqlite3.connect(store.DB_PATH) as conn:
        rows = conn.execute("SELECT game_id, pick, odds, stake FROM signals").fetchall()
    assert rows and rows[0][0] == "G1" and "HOM -2.5" in rows[0][1]
