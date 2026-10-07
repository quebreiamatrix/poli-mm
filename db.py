"""Logger SQLite (Fase 0) — grava livro, trades, nossos fills e resolucoes.

Escrita em thread separada (fila) pra nao travar o loop do WebSocket.
"""
import json
import os
import queue
import sqlite3
import threading
import time

Q = queue.Queue()
_path = None
_last_tick = {}

SCHEMA = """
CREATE TABLE IF NOT EXISTS markets(
  slug TEXT PRIMARY KEY, asset TEXT, condition TEXT, tok_up TEXT, tok_down TEXT, start INT, end INT);
CREATE TABLE IF NOT EXISTS ticks(
  ts INT, token TEXT, bb REAL, ba REAL, bb_sz REAL, ba_sz REAL);
CREATE TABLE IF NOT EXISTS trades(
  ts INT, token TEXT, condition TEXT, price REAL, size REAL, side TEXT, tx TEXT);
CREATE TABLE IF NOT EXISTS la_fills(
  ts INT, token TEXT, outcome TEXT, price REAL, size REAL, mid REAL, queue REAL);
CREATE TABLE IF NOT EXISTS resolutions(
  condition TEXT PRIMARY KEY, winner TEXT, ts INT);
CREATE INDEX IF NOT EXISTS ix_ticks_ts ON ticks(ts);
CREATE INDEX IF NOT EXISTS ix_trades_ts ON trades(ts);
CREATE INDEX IF NOT EXISTS ix_lafill_ts ON la_fills(ts);
"""


def init(path):
    global _path
    _path = path
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    con.commit()
    con.close()
    threading.Thread(target=_writer, daemon=True).start()
    return path


def _writer():
    con = sqlite3.connect(_path)
    cur = con.cursor()
    while True:
        batch = []
        try:
            while len(batch) < 500:
                batch.append(Q.get(timeout=1))
        except queue.Empty:
            pass
        if not batch:
            continue
        for sql, args in batch:
            try:
                cur.execute(sql, args)
            except Exception:
                pass
        con.commit()


def _ins(sql, args):
    if _path:
        Q.put((sql, args))


def market(slug, asset, condition, tok_up, tok_down, start, end):
    _ins("INSERT OR REPLACE INTO markets VALUES (?,?,?,?,?,?,?)",
         (slug, asset, condition, tok_up, tok_down, start, end))


def tick(token, bb, ba, bb_sz, ba_sz, now=None):
    if bb is None and ba is None:
        return
    now = int(now or time.time())
    if now - _last_tick.get(token, 0) < 1:      # amostra ~1/s por token
        return
    _last_tick[token] = now
    _ins("INSERT INTO ticks VALUES (?,?,?,?,?,?)", (now, token, bb, ba, bb_sz, ba_sz))


def trade(ts, token, condition, price, size, side, tx):
    _ins("INSERT INTO trades VALUES (?,?,?,?,?,?,?)",
         (int(ts), token, condition, price, size, side, tx))


def la_fill(ts, token, outcome, price, size, mid, queue_ahead):
    _ins("INSERT INTO la_fills VALUES (?,?,?,?,?,?,?)",
         (int(ts), token, outcome, price, size, mid, queue_ahead))


def resolution(condition, winner, ts=None):
    _ins("INSERT OR REPLACE INTO resolutions VALUES (?,?,?)",
         (condition, winner, int(ts or time.time())))
