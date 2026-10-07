"""Minerador de carteiras consistentes — curva MARCADA (v2/user-pnl).

Fonte: https://data-api.polymarket.com/v2/user-pnl?user=<addr>&interval=all&fidelity=1d
  points[].economic_pnl = PnL economico acumulado (realizado + nao-realizado + fees + income)
  -> e' a MESMA curva do grafico do perfil (drawdown real).

Rankeia por: MENOR DRAWDOWN % + consistencia + lucro. Valida e descarta serie flat.
"""
import json
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import net

net.install(verbose=False)
D = "https://data-api.polymarket.com"


def get(url, tries=3, timeout=25):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(
                    url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}), timeout=timeout) as r:
                return json.loads(r.read().decode())
        except Exception:
            if i == tries - 1:
                return None


def candidates():
    seen = {}
    for period in ("all", "month", "week"):
        for off in range(0, 300, 50):
            d = get("%s/v1/leaderboard?timePeriod=%s&category=overall&orderBy=PNL&limit=50&offset=%d" % (D, period, off))
            if not d:
                break
            for e in d:
                a = (e.get("proxyWallet") or "").lower()
                if a:
                    seen.setdefault(a, {"addr": a, "name": e.get("userName") or ""})
    return list(seen.values())


def score(w):
    d = get("%s/v2/user-pnl?user=%s&interval=all&fidelity=1d" % (D, w["addr"]))
    if not d or not isinstance(d, dict):
        return None
    pts = (d.get("data") or {}).get("points") or []
    if len(pts) < 20:
        return None
    ser = [(int(p.get("timestamp") or 0), float(p.get("economic_pnl") or 0)) for p in pts]
    ser.sort()
    fin = ser[-1][1]
    if fin <= 0:
        return None
    lo, hi = min(v for _, v in ser), max(v for _, v in ser)
    if hi - lo < 0.05 * fin:      # serie flat/degenerada -> descarta
        return None
    peak, dd = -1e18, 0.0
    for t, v in ser:
        peak = max(peak, v)
        dd = max(dd, peak - v)
    days = max(1, round((ser[-1][0] - ser[0][0]) / 86400))
    ups = sum(1 for a, b in zip(ser, ser[1:]) if b[1] >= a[1])
    w.update({"final": round(fin, 2), "maxdd": round(dd, 2), "dd_pct": round(100 * dd / fin, 1),
              "days": days, "pts": len(ser), "upr": round(100 * ups / (len(ser) - 1), 1),
              "recovery": round(fin / dd, 2) if dd > 1e-9 else 999})
    return w


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    cands = candidates()
    print("candidatos:", len(cands))
    out = []
    with ThreadPoolExecutor(max_workers=10) as ex:
        for w in ex.map(score, cands):
            if w:
                out.append(w)
    print("com curva valida:", len(out))
    out = [w for w in out if w["days"] >= 20 and w["final"] >= 500]
    out.sort(key=lambda w: (w["dd_pct"], -w["recovery"], -w["upr"]))
    print("\n%-14s %-20s %9s %8s %6s %5s %6s %8s" %
          ("wallet", "nome", "pnl$", "maxDD", "DD%", "dias", "up%", "recov"))
    for w in out[:N]:
        print("%-14s %-20s %9.0f %8.0f %6.1f %5d %6.1f %8.2f" % (
            w["addr"][:12], (w["name"] or "")[:20], w["final"], w["maxdd"], w["dd_pct"],
            w["days"], w["upr"], w["recovery"]))
    json.dump(out[:N], open("miner_top.json", "w"), indent=1)
    print("\nsalvo miner_top.json")


if __name__ == "__main__":
    main()
