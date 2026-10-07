import json
import urllib.request
import net

net.install(verbose=False)
s = json.load(urllib.request.urlopen("http://localhost:8800/state", timeout=6))
print("errors:", s["errors"][-6:])
print("totais: realizado=%.2f aberto=%.2f investido=%.2f mercados=%d" % (
    s["totals"]["pnl"], s["totals"]["open_pnl"], s["totals"]["open_cost"], s["totals"]["markets"]))
now = int(__import__("time").time())
for m in s["markets"]:
    print("  ABERTO", m["slug"], "end_age", now - m["end"], "fills", m["fills"])
for slug in ["btc-updown-5m-1791313500", "btc-updown-5m-1791313800"]:
    ev = net.get_json("https://gamma-api.polymarket.com/events?slug=%s" % slug)
    mk = ev[0]["markets"][0]
    print(slug, "closed=", mk.get("closed"), "prices=", mk.get("outcomePrices"))
