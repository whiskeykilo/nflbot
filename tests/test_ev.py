import sys
from pathlib import Path

import pytest

# Ensure the application package is importable when tests are run directly.
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core import ev


def test_american_to_implied_prob_handles_positive_and_negative_odds():
    assert pytest.approx(ev.american_to_implied_prob(200), 0.0001) == 0.3333333333333333
    assert pytest.approx(ev.american_to_implied_prob(-150), 0.0001) == 0.6


def test_expected_value_per_dollar_includes_negative_odds():
    assert pytest.approx(ev.expected_value_per_dollar(0.5, 200), 0.0001) == 0.5
    # Break-even probability gives zero expected value
    assert pytest.approx(ev.expected_value_per_dollar(0.6, -150), 0.0001) == 0.0


def test_kelly_fraction_positive_and_zero():
    assert pytest.approx(ev.kelly_fraction(0.5, 200), 0.0001) == 0.25
    # When p_true equals break-even probability the Kelly fraction is zero
    assert pytest.approx(ev.kelly_fraction(0.6, -150), 0.0001) == 0.0
