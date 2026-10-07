import net, json, urllib.request, collections, statistics
net.install(verbose=False)
D="https://data-api.polymarket.com"
def get(u): return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"}),timeout=30).read())
Ws=[("0x41e2e1ccf1e4940029af02259a31c6b89b9fa354","norm1e69"),
    ("0xd9e0aaca471f489be338fd0f91a26e8669a805f2","0xD9E0AACa"),
    ("0x6e2c0e94740c6487c4b2a4b9d0a4c40b9d2d5a9e","0x99a093?"),
    ("0x32c4922da3e5f0f4d0b3e0b0a0f5c1e0a0b0c0d0","grumbong?"),
    ("0xfc23869c29d0b3c0e0a0f5c1e0a0b0c0d0e0f000","testBruno2?")]
# usar enderecos reais do miner_active.json
rows=json.load(open("miner_active.json"))
pick=[r for r in rows if r["name"] in ("norm1e69","grumbong","testBruno2","gabigol","TommyLeePeeca") or r["addr"].startswith("0xd9e0aaca") or r["addr"].startswith("0x6e2c0e94")][:6]
for w in pick:
    A=w["addr"]
    d=get("%s/v2/user-pnl?user=%s&interval=all&fidelity=1d"%(D,A))
    pts=(d.get("data") or {}).get("points") or []
    ser=sorted((int(p["timestamp"]),float(p.get("economic_pnl") or 0)) for p in pts)
    daily=[b[1]-a[1] for a,b in zip(ser,ser[1:])]
    posd=sum(1 for x in daily if x>0)
    val=get("%s/value?user=%s"%(D,A))
    cap=val[0].get("value") if isinstance(val,list) and val else None
    tr=get("%s/trades?user=%s&limit=300&takerOnly=false"%(D,A))
    mk=collections.Counter(t["title"] for t in tr).most_common(2)
    print("\n%-14s (%s)"%(w["name"] or "?",A[:10]))
    print("  PnL total=%.0f | dias=%d | media/dia=%.0f | mediana/dia=%.0f | max/dia=%.0f | %%dias+=%.0f%%"%(
        ser[-1][1],len(ser),statistics.mean(daily),statistics.median(daily),max(daily),
        100*posd/max(1,len(daily))))
    if cap: print("  capital (value now)=%.0f -> media/dia = %.2f%% do capital"%(cap,100*statistics.mean(daily)/cap if cap else 0))
    print("  mercados:", [m[0][:45] for m in mk])
