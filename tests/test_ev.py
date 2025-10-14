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


def test_push_probability_adjusts_break_even_and_ev():
    # Without pushes the bet is -EV
    ev_no_push = ev.expected_value_per_dollar(0.5, -110, 0.0)
    assert ev_no_push < 0
    # Introduce a realistic push probability and confirm EV improves
    ev_with_push = ev.expected_value_per_dollar(0.5, -110, 0.05)
    assert pytest.approx(ev_with_push, 1e-6) == 0.00454545
    be_with_push = ev.break_even_prob(-110, 0.05)
    assert pytest.approx(be_with_push, 1e-6) == 0.497619
