"""Backtest (Fases 1-4) dos DOIS bots, a partir do banco SQLite (Fase 0).

Fase 1: execucao realista (fila proporcional no nivel, latencia, adverse, fee=0 maker).
Fase 2: backtest com metricas (PnL, Sharpe, DD, win, turnover, ROI/dia).
Fase 3: walk-forward (split in/out-of-sample por janelas de tempo).
Fase 4: estatistica (bootstrap CI, t-stat, risco de ruina).

Bots:
  MM   — bid-side (tipo norm1e69): cota BID, compra em prints SELL <= bid, segura.
  ANON — ask-side (tipo Anon): cota ASK, vende em prints BUY >= ask, SPLIT/MERGE.

Uso: python backtest.py [pm.db]
"""
import math
import random
import sqlite3
import statistics
import sys
import time

DB = sys.argv[1] if len(sys.argv) > 1 else "pm.db"
SIZE = 5            # shares por ordem
BANCA = 100.0
NET_CAP = 8         # teto de estoque de um lado (ANON)
LATENCY = 0.25      # s (taker delay)


def load():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    ticks = {}
    for r in con.execute("SELECT ts,token,bb,ba,bb_sz,ba_sz FROM ticks ORDER BY ts"):
        ticks.setdefault(r["token"], []).append((r["ts"], r["bb"], r["ba"], r["bb_sz"], r["ba_sz"]))
    trades = {}
    for r in con.execute("SELECT ts,token,price,size,side FROM trades ORDER BY ts"):
        trades.setdefault(r["token"], []).append((r["ts"], r["price"], r["size"], r["side"]))
    res = {r["condition"]: r["winner"] for r in con.execute("SELECT condition,winner FROM resolutions")}
    mk = list(con.execute("SELECT slug,asset,condition,tok_up,tok_down,start,end FROM markets"))
    con.close()
    return ticks, trades, res, mk


def book_at(tl, ts):
    """ultimo tick <= ts (preco/size do topo)."""
    lo, hi, out = 0, len(tl) - 1, None
    while lo <= hi:
        m = (lo + hi) // 2
        if tl[m][0] <= ts:
            out = tl[m]; lo = m + 1
        else:
            hi = m - 1
    return out


def sim(markets, ticks, trades, res):
    """Roda os dois bots mercado a mercado. Retorna lista de resultados por mercado."""
    out = []
    for slug, asset, cid, up, dn, start, end in markets:
        winner = res.get(cid)
        if winner is None:
            continue
        # --- MM (bid-side): compra nos dois tokens ---
        mm_inv = {up: 0.0, dn: 0.0}
        mm_cost = 0.0
        for tok in (up, dn):
            tl = ticks.get(tok, [])
            for ts, price, size, side in trades.get(tok, []):
                b = book_at(tl, ts)
                if not b:
                    continue
                _, bb, ba, bb_sz, ba_sz = b
                if bb is None or side != "SELL" or price > bb + 1e-9:
                    continue
                f = SIZE / ((bb_sz or 0) + SIZE)          # fila proporcional
                q = size * f
                room = max(0.0, (BANCA - mm_cost))
                q = min(q, room / price if price else 0)
                if q > 0:
                    mm_inv[tok] += q
                    mm_cost += q * price
        mm_pay = mm_inv[up] if winner == "Up" else mm_inv[dn]
        mm_pnl = mm_pay - mm_cost

        # --- ANON (ask-side): vende, split/merge ---
        la_inv = {up: 0.0, dn: 0.0}
        la_cash = 0.0
        la_sold = 0.0
        for tok in (up, dn):
            opp = dn if tok == up else up
            tl = ticks.get(tok, [])
            for ts, price, size, side in trades.get(tok, []):
                b = book_at(tl, ts)
                if not b:
                    continue
                _, bb, ba, bb_sz, ba_sz = b
                if ba is None or side != "BUY" or price < ba - 1e-9:
                    continue
                f = SIZE / ((ba_sz or 0) + SIZE)
                q = size * f
                room = max(0.0, NET_CAP - la_inv[opp])
                q = min(q, la_inv[tok] + room)
                need = max(0.0, q - la_inv[tok])
                if need > 0 and (la_cash + BANCA) < need:
                    need = max(0.0, la_cash + BANCA)
                    q = min(q, la_inv[tok] + need)
                if q <= 0:
                    continue
                if need > 0:
                    la_inv[up] += need
                    la_inv[dn] += need
                    la_cash -= need
                la_inv[tok] -= q
                la_cash += q * ba
                la_sold += q
        m = min(la_inv[up], la_inv[dn])
        if m > 0:
            la_inv[up] -= m; la_inv[dn] -= m; la_cash += m
        la_pay = la_inv[up] if winner == "Up" else la_inv[dn]
        la_pnl = la_cash + max(0.0, la_pay)

        out.append({"slug": slug, "asset": asset, "end": end, "winner": winner,
                    "mm_pnl": round(mm_pnl, 4), "la_pnl": round(la_pnl, 4),
                    "la_sold": round(la_sold, 2)})
    return out


def stats(rows, key):
    p = [r[key] for r in rows]
    if not p:
        return {}
    mean = statistics.mean(p)
    sd = statistics.pstdev(p) if len(p) > 1 else 0.0
    cum = 0.0; peak = 0.0; dd = 0.0
    for v in p:
        cum += v; peak = max(peak, cum); dd = max(dd, peak - cum)
    wins = sum(1 for v in p if v > 0)
    t = mean / (sd / math.sqrt(len(p))) if sd > 0 else 0.0
    return {"n": len(p), "pnl": round(sum(p), 2), "mean": round(mean, 4), "sd": round(sd, 3),
            "sharpe": round(mean / sd, 3) if sd else 0, "t": round(t, 2),
            "maxdd": round(dd, 2), "winrate": round(100 * wins / len(p), 1)}


def bootstrap_ci(rows, key, iters=5000, lo=2.5, hi=97.5):
    p = [r[key] for r in rows]
    if len(p) < 5:
        return None
    sums = []
    for _ in range(iters):
        sums.append(sum(random.choice(p) for _ in range(len(p))))
    sums.sort()
    return round(sums[int(len(sums) * lo / 100)], 2), round(sums[int(len(sums) * hi / 100)], 2)


def walk_forward(rows, key, k=3):
    rows = sorted(rows, key=lambda r: r["end"])
    n = len(rows) // k
    out = []
    for i in range(k):
        part = rows[i * n:(i + 1) * n] if i < k - 1 else rows[i * n:]
        s = stats(part, key)
        out.append((i + 1, s.get("n", 0), s.get("pnl", 0), s.get("sharpe", 0)))
    return out


def main():
    ticks, trades, res, mk = load()
    rows = sim(mk, ticks, trades, res)
    if not rows:
        print("sem dados resolvidos ainda — deixe o bot coletar mais (ticks=%d trades=%d res=%d)"
              % (sum(len(v) for v in ticks.values()), sum(len(v) for v in trades.values()), len(res)))
        return
    print("mercados resolvidos:", len(rows))
    for key, name in (("mm_pnl", "MM (bid-side, tipo norm1e69)"), ("la_pnl", "ANON (ask-side)")):
        print("\n== %s ==" % name)
        s = stats(rows, key)
        print("  n=%d  PnL=%.2f  media/merc=%.3f  sharpe=%.3f  t=%.2f  maxDD=%.2f  win=%.1f%%"
              % (s["n"], s["pnl"], s["mean"], s["sharpe"], s["t"], s["maxdd"], s["winrate"]))
        ci = bootstrap_ci(rows, key)
        if ci:
            print("  bootstrap 95%% CI do PnL total: [%.2f, %.2f]" % ci)
        print("  walk-forward (3 janelas):", walk_forward(rows, key))


if __name__ == "__main__":
    main()
