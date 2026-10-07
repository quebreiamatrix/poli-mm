import net, json, urllib.request, collections
net.install(verbose=False)
A="0x5916ce250c0b3e32eed3303ffb2938cab0b42a0b"; D="https://data-api.polymarket.com"
def get(u): return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"}),timeout=30).read())
act=get("%s/activity?user=%s&limit=500"%(D,A))
by=collections.defaultdict(list)
for a in act: by[a.get("type")].append(a)
for typ in ("SPLIT","MERGE","REDEEM","TRADE"):
    xs=by.get(typ,[])
    print("\n== %s (%d) =="%(typ,len(xs)))
    for a in xs[:2]:
        print("  ", json.dumps({k:a.get(k) for k in ("type","size","usdcSize","price","outcome","title","side")})[:220])
# soma usdc por tipo
for typ in ("SPLIT","MERGE","REDEEM","TRADE"):
    xs=by.get(typ,[])
    u=sum((a.get("usdcSize") or 0) for a in xs)
    print("%-7s n=%3d soma usdcSize=%.0f"%(typ,len(xs),u))
