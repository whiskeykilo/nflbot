import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.spreads import p_fav_half, map_hr_to_probs


def test_p_fav_half_exact_and_interpolation():
    ladder = {-7.5: 0.52, -6.5: 0.60}
    p, interp = p_fav_half(-7.5, ladder, max_gap=1.0)
    assert interp is False and pytest.approx(p, 1e-6) == 0.52
    # Interpolate midway to -7.0
    p2, interp2 = p_fav_half(-7.0, ladder, max_gap=1.0)
    assert interp2 is True and pytest.approx(p2, 1e-6) == 0.56


def test_map_hr_to_probs_whole_number_pushes():
    ladder = {-7.5: 0.52, -6.5: 0.60}
    # Favorite -7.0
    p_win, p_push, p_lose, meta = map_hr_to_probs("home", -7.0, ladder, max_gap=1.0)
    assert meta["whole"] is True
    assert pytest.approx(p_win, 1e-6) == 0.52
    assert pytest.approx(p_push, 1e-6) == 0.08
    assert pytest.approx(p_win + p_push + p_lose, 1e-6) == 1.0
    # Dog +7.0
    p_win_d, p_push_d, p_lose_d, _ = map_hr_to_probs("away", +7.0, ladder, max_gap=1.0)
    assert pytest.approx(p_win_d, 1e-6) == 0.40
    assert pytest.approx(p_push_d, 1e-6) == 0.08
    assert pytest.approx(p_win_d + p_push_d + p_lose_d, 1e-6) == 1.0


def test_map_hr_to_probs_half_points():
    ladder = {-2.5: 0.54}
    # Favorite -2.5
    p_win, p_push, p_lose, meta = map_hr_to_probs("home", -2.5, ladder)
    assert meta["whole"] is False and pytest.approx(p_win, 1e-6) == 0.54 and pytest.approx(p_push, 1e-6) == 0.0
    # Dog +2.5
    p_win_d, p_push_d, p_lose_d, meta_d = map_hr_to_probs("away", +2.5, ladder)
    assert meta_d["whole"] is False and pytest.approx(p_win_d, 1e-6) == 0.46 and pytest.approx(p_push_d, 1e-6) == 0.0


def test_map_hr_to_probs_respects_max_gap():
    ladder = {-9.5: 0.48, -3.5: 0.62}
    assert map_hr_to_probs("home", -7.0, ladder, max_gap=1.0) is None

