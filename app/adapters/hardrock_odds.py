# Replace with a real odds source (API that includes Hard Rock or your scraper).
def fetch_hr_nfl_moneylines()->list[dict]:
    return [{
      "game_id":"DEMO1","home":"JAX","away":"MIA","start_utc":"2025-09-07T17:00:00Z",
      "market":"ML","odds_home":-110,"odds_away":+100
    }]