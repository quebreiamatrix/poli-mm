"""Minerador de BOTS ATIVOS e consistentes (tipo norm1e69).

1) pega a fita global de trades recentes e conta a frequencia por carteira
   -> quem esta operando AGORA (HFT/arb)
2) para cada ativa, mede: nº trades/h, idade do ultimo trade, curva marcada (v2)
   -> filtra por atividade + consistencia (DD baixo)
"""
import json
import sys
import time
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import net

net.install(verbose=False)
D = "https://data-api.polymarket.com"
NOW = int(time.time())
FIREHOSE = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
TOPN = int(sys.argv[2]) if len(sys.argv) > 2 else 40


def get(url, tries=3, timeout=30):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(
                    url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}), timeout=timeout) as r:
                return json.loads(r.read().decode())
        except Exception:
            if i == tries - 1:
                return None


def active_wallets():
    tr = get("%s/trades?limit=%d&takerOnly=false" % (D, FIREHOSE))
    if not tr:
        return {}
    cnt, name, last = Counter(), {}, {}
    for t in tr:
        a = (t.get("proxyWallet") or "").lower()
        if not a:
            continue
        cnt[a] += 1
        name.setdefault(a, t.get("name") or t.get("pseudonym") or "")
        last[a] = max(last.get(a, 0), int(t.get("timestamp") or 0))
    span = max(1, (NOW - min(last.values())))
    out = {}
    for a, c in cnt.most_common(TOPN * 4):
        out[a] = {"addr": a, "name": name.get(a, ""), "tr": c,
                  "age": NOW - last[a], "rate": round(c / (span / 3600.0), 1)}
    return out


def enrich(w):
    # fita do wallet (p/ taxa horaria + idade)
    tr = get("%s/trades?user=%s&limit=500&takerOnly=false" % (D, w["addr"]))
    if tr:
        ts = sorted(int(t.get("timestamp") or 0) for t in tr)
        w["age"] = NOW - ts[-1]
        w["h1"] = sum(1 for x in ts if x >= NOW - 3600)
    # curva marcada (consistencia)
    d = get("%s/v2/user-pnl?user=%s&interval=all&fidelity=1d" % (D, w["addr"]))
    if not d or not isinstance(d, dict):
        return None
    pts = (d.get("data") or {}).get("points") or []
    if len(pts) < 15:
        return None
    ser = sorted((int(p.get("timestamp") or 0), float(p.get("economic_pnl") or 0)) for p in pts)
    fin = ser[-1][1]
    if fin <= 0:
        return None
    lo, hi = min(v for _, v in ser), max(v for _, v in ser)
    if hi - lo < 0.05 * fin:
        return None
    peak, dd = -1e18, 0.0
    for t, v in ser:
        peak = max(peak, v)
        dd = max(dd, peak - v)
    days = max(1, round((ser[-1][0] - ser[0][0]) / 86400))
    ups = sum(1 for a, b in zip(ser, ser[1:]) if b[1] >= a[1])
    w.update({"final": round(fin, 2), "dd_pct": round(100 * dd / fin, 1), "maxdd": round(dd, 2),
              "days": days, "upr": round(100 * ups / (len(ser) - 1), 1),
              "recov": round(fin / dd, 2) if dd > 1e-9 else 999})
    return w


def main():
    act = active_wallets()
    print("carteiras ativas na fita:", len(act))
    out = []
    with ThreadPoolExecutor(max_workers=12) as ex:
        for w in ex.map(enrich, list(act.values())):
            if w:
                out.append(w)
    # ativas AGORA (ultimo trade < 30 min) e com giro
    act2 = [w for w in out if w["age"] <= 1800 and w["h1"] >= 5 and w["days"] >= 7]
    print("ativas+consistentes:", len(act2))
    act2.sort(key=lambda w: (w["dd_pct"], -w["h1"], -w["final"]))
    print("\n%-14s %-18s %5s %5s %6s %8s %6s %6s %5s %6s" %
          ("wallet", "nome", "h1", "tr", "age_m", "pnl$", "DD%", "up%", "dias", "recov"))
    for w in act2[:TOPN]:
        print("%-14s %-18s %5d %5d %6d %8.0f %6.1f %6.1f %5d %6.1f" % (
            w["addr"][:12], (w["name"] or "")[:18], w["h1"], w["tr"], w["age"] // 60,
            w["final"], w["dd_pct"], w["upr"], w["days"], w["recov"]))
    json.dump(act2[:TOPN], open("miner_active.json", "w"), indent=1)
    print("\nsalvo miner_active.json")


if __name__ == "__main__":
    main()
