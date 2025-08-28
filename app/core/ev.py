def american_to_implied_prob(odds:int)->float:
    return 100/(odds+100) if odds>0 else abs(odds)/(abs(odds)+100)

def expected_value_per_dollar(p_true:float, odds:int)->float:
    b = (odds/100) if odds>0 else (100/abs(odds))
    return p_true*b - (1-p_true)

def kelly_fraction(p_true:float, odds:int)->float:
    b = (odds/100) if odds>0 else (100/abs(odds))
    return (b*p_true - (1-p_true))/b