import net, json, urllib.request, statistics
net.install(verbose=False)
D="https://data-api.polymarket.com"
def get(u): return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"}),timeout=30).read())
rows=json.load(open("miner_clean.json"))
print("%-13s %-15s %8s %8s %8s %6s %6s"%("wallet","nome","ticket_med","ticket_p90","ticket_max","DD%","7d$"))
for w in rows:
    tr=get("%s/trades?user=%s&limit=500&takerOnly=false"%(D,w["addr"]))
    notl=sorted((t["size"]*t["price"]) for t in tr if t.get("price") and t.get("size"))
    if not notl: continue
    med=statistics.median(notl); p90=notl[int(len(notl)*0.9)]; mx=max(notl)
    print("%-13s %-15s %8.1f %8.1f %8.0f %6.1f %6.0f"%(w["addr"][:12],(w["name"] or "")[:15],med,p90,mx,w["dd_pct"],w["recent7"]))
