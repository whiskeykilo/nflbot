def american_to_implied_prob(odds: int) -> float:
    return 100 / (odds + 100) if odds > 0 else abs(odds) / (abs(odds) + 100)

def payout_multiple(odds: int) -> float:
    """Return net payout multiple b per $1 stake for American odds.

    Example: +120 -> 1.2, -150 -> 100/150 ~= 0.6667
    """
    return (odds / 100) if odds > 0 else (100 / abs(odds))

def break_even_prob(odds: int, p_push: float = 0.0) -> float:
    """Break-even win probability accounting for push probability.

    p_win_break_even = (1 - p_push) / (b + 1)
    """
    b = payout_multiple(odds)
    return (1.0 - max(0.0, min(1.0, p_push))) / (b + 1.0)

def expected_value_per_dollar(p_win: float, odds: int, p_push: float = 0.0) -> float:
    """Expected profit per $1 stake accounting for pushes.

    EV = p_win*b - p_loss, where p_loss = 1 - p_win - p_push.
    """
    b = payout_multiple(odds)
    p_win = max(0.0, min(1.0, p_win))
    p_push = max(0.0, min(1.0, p_push))
    return p_win * b - (1.0 - p_win - p_push)

def kelly_fraction(p_win: float, odds: int, p_push: float = 0.0) -> float:
    """Kelly fraction with pushes using q = 1 - p_win - p_push.

    f* = (b*p - q)/b
    """
    b = payout_multiple(odds)
    p_win = max(0.0, min(1.0, p_win))
    p_push = max(0.0, min(1.0, p_push))
    q = 1.0 - p_win - p_push
    return (b * p_win - q) / b
