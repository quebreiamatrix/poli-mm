"""Top cripto LIMPO: ativo agora + PnL recente>0 + consistencia. Sem fantasma."""
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


def get(url, tries=3, timeout=30):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(
                    url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}), timeout=timeout) as r:
                return json.loads(r.read().decode())
        except Exception:
            if i == tries - 1:
                return None


def active():
    tr = get("%s/trades?limit=10000&takerOnly=false" % D)
    cnt, nm, last = Counter(), {}, {}
    for t in tr or []:
        a = (t.get("proxyWallet") or "").lower()
        if not a:
            continue
        cnt[a] += 1
        nm.setdefault(a, t.get("name") or t.get("pseudonym") or "")
        last[a] = max(last.get(a, 0), int(t.get("timestamp") or 0))
    return [{"addr": a, "name": nm.get(a, ""), "age": NOW - last[a]} for a, _ in cnt.most_common(300)]


def enrich(w):
    tr = get("%s/trades?user=%s&limit=500&takerOnly=false" % (D, w["addr"]))
    if not tr:
        return None
    ts = sorted(int(t.get("timestamp") or 0) for t in tr)
    w["age"] = NOW - ts[-1]
    w["h1"] = sum(1 for x in ts if x >= NOW - 3600)
    crypto = sum(1 for t in tr if "Up or Down" in (t.get("title") or ""))
    w["cr"] = round(100 * crypto / len(tr))
    d = get("%s/v2/user-pnl?user=%s&interval=all&fidelity=1d" % (D, w["addr"]))
    pts = (d or {}).get("data", {}).get("points") if isinstance(d, dict) else None
    if not pts or len(pts) < 10:
        return None
    ser = sorted((int(p.get("timestamp") or 0), float(p.get("economic_pnl") or 0)) for p in pts)
    fin = ser[-1][1]
    lo, hi = min(v for _, v in ser), max(v for _, v in ser)
    if fin <= 0 or hi - lo < 0.05 * fin:
        return None
    # PnL dos ultimos 7 dias
    ref = next((v for t, v in reversed(ser) if t <= NOW - 7 * 86400), ser[0][1])
    w["recent7"] = round(fin - ref, 2)
    peak, dd = -1e18, 0.0
    for t, v in ser:
        peak = max(peak, v); dd = max(dd, peak - v)
    ups = sum(1 for a, b in zip(ser, ser[1:]) if b[1] >= a[1])
    w.update({"final": round(fin, 2), "dd_pct": round(100 * dd / fin, 1), "maxdd": round(dd, 2),
              "days": max(1, round((ser[-1][0] - ser[0][0]) / 86400)),
              "upr": round(100 * ups / (len(ser) - 1), 1),
              "last_pt_age_h": round((NOW - ser[-1][0]) / 3600, 1)})
    return w


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    out = []
    with ThreadPoolExecutor(max_workers=12) as ex:
        for w in ex.map(enrich, active()):
            if w:
                out.append(w)
    # filtros anti-fantasma
    ok = [w for w in out if w["age"] <= 1800 and w["h1"] >= 3 and w["cr"] >= 50
          and w["recent7"] > 0 and w["days"] >= 7]
    ok.sort(key=lambda w: (w["dd_pct"], -w["upr"], -w["final"]))
    print("crypto ativos+recentes+consistentes:", len(ok))
    print("%-14s %-16s %4s %7s %8s %8s %6s %6s %5s %5s" %
          ("wallet", "nome", "cr%", "h1", "pnl$", "7d$", "DD%", "up%", "dias", "idade"))
    for w in ok[:N]:
        print("%-14s %-16s %4d %7d %8.0f %8.0f %6.1f %6.1f %5d %5d" %
              (w["addr"][:12], (w["name"] or "")[:16], w["cr"], w["h1"], w["final"], w["recent7"],
               w["dd_pct"], w["upr"], w["days"], w["age"] // 60))
    json.dump(ok[:N], open("miner_clean.json", "w"), indent=1)
    print("\nsalvo miner_clean.json")


if __name__ == "__main__":
    main()
