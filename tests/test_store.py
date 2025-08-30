import sqlite3
import sys
from pathlib import Path

import pytest

# Ensure the application package is importable when tests are run directly.
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core import store


def test_save_signal_persists_data_with_negative_odds_and_zero_kelly(tmp_path):
    db_file = tmp_path / "signals.sqlite"
    store.DB_PATH = str(db_file)
    sig = {
        "game_id": "G1",
        "market": "ML",
        "pick": "HOME",
        "odds": -120,  # negative odds edge case
        "p_true": 0.55,
        "edge": 0.05,
        "kelly": 0.0,  # zero kelly edge case
        "stake": 10.0,
    }

    store.save_signal(sig)

    with sqlite3.connect(store.DB_PATH) as conn:
        row = conn.execute(
            "SELECT game_id, market, pick, odds, kelly FROM signals"
        ).fetchone()
    assert row == ("G1", "ML", "HOME", -120, 0.0)


def test_save_signal_requires_all_fields(tmp_path):
    store.DB_PATH = str(tmp_path / "signals.sqlite")
    bad_sig = {"game_id": "G1"}  # Missing required fields
    with pytest.raises(KeyError):
        store.save_signal(bad_sig)
