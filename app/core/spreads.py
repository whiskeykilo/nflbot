from __future__ import annotations

from typing import Dict, Tuple, Optional


def p_fav_half(target: float, ladder: Dict[float, float], max_gap: Optional[float] = None) -> Optional[Tuple[float, bool]]:
    """Return fair probability that the favorite covers target half-spread.

    Ladder maps favorite half/whole spreads (negative numbers for fav) to
    de‑vig probabilities of favorite covering at that spread. Linear
    interpolation is used between nearest neighbors if needed.
    """
    if target in ladder:
        return ladder[target], False
    if not ladder:
        return None
    xs = sorted(ladder.keys())
    lo = None
    hi = None
    for x in xs:
        if x <= target:
            lo = x
        if x >= target and hi is None:
            hi = x
    if lo is None or hi is None:
        return None
    if lo == hi:
        return ladder[lo], False
    # Enforce maximum interpolation gap if provided
    if max_gap is not None:
        if abs(target - lo) > max_gap or abs(hi - target) > max_gap:
            return None
    p_lo = ladder[lo]
    p_hi = ladder[hi]
    t = (target - lo) / (hi - lo)
    return (p_lo + t * (p_hi - p_lo)), True


def map_hr_to_probs(
    side: str,
    s_hr: float,
    ladder: Dict[float, float],
    max_gap: Optional[float] = None,
) -> Optional[Tuple[float, float, float, Dict[str, bool]]]:
    """Map a Hard Rock contract to (p_win, p_push, p_lose) using a favorite ladder.

    side: 'home' or 'away' is not used directly; favorite/dog is inferred from s_hr.
    s_hr: HR spread for the selected side (negative = favorite, positive = dog).
    ladder: favorite ladder mapping fav spreads (negative) to p_fav_cover.
    """
    # Determine favorite/dog by line sign for this side
    if s_hr is None:
        return None
    # Half point: push ~ 0
    meta = {"whole": False, "interpolated": False}
    if abs(s_hr - round(s_hr)) > 1e-6:  # non-integer -> treat as half-point
        if s_hr < 0:  # favorite at -x.5
            res = p_fav_half(s_hr, ladder, max_gap)
            if res is None:
                return None
            p_win, interp = res
            meta["interpolated"] = meta["interpolated"] or bool(interp)
            p_push = 0.0
            p_lose = 1.0 - p_win
            return p_win, p_push, p_lose, meta
        else:  # underdog at +x.5
            res = p_fav_half(-abs(s_hr), ladder, max_gap)
            if res is None:
                return None
            p_fav, interp = res
            meta["interpolated"] = meta["interpolated"] or bool(interp)
            p_win = 1.0 - p_fav
            p_push = 0.0
            p_lose = 1.0 - p_win
            return p_win, p_push, p_lose, meta
    # Whole number: use adjacent halves around the whole
    meta["whole"] = True
    n = abs(int(round(s_hr)))
    s_lo = -(n - 0.5)
    s_hi = -(n + 0.5)
    r_lo = p_fav_half(s_lo, ladder, max_gap)
    r_hi = p_fav_half(s_hi, ladder, max_gap)
    if r_lo is None or r_hi is None:
        return None
    p_lo, interp_lo = r_lo
    p_hi, interp_hi = r_hi
    meta["interpolated"] = meta["interpolated"] or bool(interp_lo or interp_hi)
    p_push_fav = max(0.0, p_lo - p_hi)
    if s_hr < 0:  # favorite at -n.0
        p_win = p_hi
        p_push = p_push_fav
        p_lose = 1.0 - p_win - p_push
        return p_win, p_push, p_lose, meta
    else:  # underdog at +n.0
        p_win = 1.0 - p_lo
        p_push = p_push_fav
        p_lose = 1.0 - p_win - p_push
        return p_win, p_push, p_lose, meta
