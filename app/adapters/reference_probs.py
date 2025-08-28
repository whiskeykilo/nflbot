from app.core.ev import american_to_implied_prob
def _devig(p1:float,p2:float):
    s=p1+p2
    return (p1/s,p2/s) if s>0 else (0.5,0.5)
def reference_probs_for(games:list[dict])->dict:
    out={}
    for g in games:
        p_h = american_to_implied_prob(g["odds_home"])
        p_a = american_to_implied_prob(g["odds_away"])
        p_h,p_a=_devig(p_h,p_a)
        out[g["game_id"]]={"p_home":p_h,"p_away":p_a}
    return out