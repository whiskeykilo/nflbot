import sys
from pathlib import Path

import pytest

# Ensure the application package is importable when tests are run directly.
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app import main


def test_spread_threshold_defaults_to_three_percent_floor():
    assert main._spread_edge_threshold({}, 2.5) == pytest.approx(0.03, abs=1e-9)


def test_spread_threshold_increases_near_key_numbers_when_interpolated():
    meta = {"interpolated": True}
    assert main._spread_edge_threshold(meta, 3.0) == pytest.approx(0.04, abs=1e-9)


def test_spread_threshold_increases_for_whole_number_lines():
    meta = {"whole": True}
    assert main._spread_edge_threshold(meta, -6.0) == pytest.approx(0.035, abs=1e-9)


def test_alert_must_clear_threshold():
    thr = main._spread_edge_threshold({}, 2.5)
    low_edge = {"market": "SPREAD", "edge": 0.029, "threshold": thr}
    high_edge = {"market": "SPREAD", "edge": 0.031, "threshold": thr}
    assert not main._passes_threshold(low_edge)
    assert main._passes_threshold(high_edge)


def test_moneyline_threshold_uses_three_percent_floor():
    alert = {"market": "ML", "edge": 0.025, "threshold": main.BASE_ML_EDGE}
    assert not main._passes_threshold(alert)
    alert["edge"] = 0.031
    assert main._passes_threshold(alert)
