import sqlite3
import time

DB_PATH = "/data/bets.sqlite"
DDL = """
CREATE TABLE IF NOT EXISTS signals(
  id INTEGER PRIMARY KEY,
  ts INTEGER, game_id TEXT, market TEXT, pick TEXT,
  odds INTEGER, p_true REAL, edge REAL, kelly REAL, stake REAL, status TEXT
);
"""


def db():
    c = sqlite3.connect(DB_PATH)
    c.execute(DDL)
    return c


def save_signal(sig: dict):
    with db() as c:
        c.execute(
            """INSERT INTO signals(ts,game_id,market,pick,odds,p_true,edge,kelly,stake,status)
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
