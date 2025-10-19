import sqlite3, time
DB_PATH = "/data/bets.sqlite"
DDL = """
CREATE TABLE IF NOT EXISTS signals(
  id INTEGER PRIMARY KEY,
  ts INTEGER, game_id TEXT, market TEXT, pick TEXT,
  odds INTEGER, p_true REAL, edge REAL, kelly REAL, stake REAL, status TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS signals_unique
  ON signals(game_id, market, pick, odds);
"""
def db():
    c = sqlite3.connect(DB_PATH); c.executescript(DDL); return c
def save_signal(sig:dict) -> bool:
    with db() as c:
        cur = c.execute(
            """INSERT OR IGNORE INTO signals(ts,game_id,market,pick,odds,p_true,edge,kelly,stake,status)
                     VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                int(time.time()),
                sig["game_id"],
                sig["market"],
                sig["pick"],
                sig["odds"],
                sig["p_true"],
                sig["edge"],
                sig["kelly"],
                sig["stake"],
                "NEW",
            ),
        )
        return bool(cur.rowcount)
