import net, json, urllib.request, collections
net.install(verbose=False)
D="https://data-api.polymarket.com"
def get(u): return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"}),timeout=30).read())
rows=json.load(open("miner_active.json"))
out=[]
for w in rows:
    tr=get("%s/trades?user=%s&limit=200&takerOnly=false"%(D,w["addr"]))
    if not tr: continue
    crypto=sum(1 for t in tr if "Up or Down" in (t.get("title") or ""))
    frac=crypto/len(tr)
    if frac>=0.5:
        w=dict(w); w["crypto_pct"]=round(100*frac)
        out.append(w)
print("crypto (>=50%% dos trades):",len(out))
out.sort(key=lambda w:(w["dd_pct"],-w["upr"],-w["final"]))
print("%-14s %-16s %4s %8s %6s %6s %5s %6s %8s"%("wallet","nome","cr%","pnl$","DD%","up%","dias","h1","recov"))
for w in out[:12]:
    print("%-14s %-16s %4d %8.0f %6.1f %6.1f %5d %6d %8.1f"%(w["addr"][:12],(w["name"] or "")[:16],w["crypto_pct"],w["final"],w["dd_pct"],w["upr"],w["days"],w["h1"],w["recov"]))
json.dump(out[:10],open("miner_crypto.json","w"),indent=1)
