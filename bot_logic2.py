import net, json, urllib.request, collections, statistics
net.install(verbose=False)
A="0xd9e0aaca471f489be338fd0f91a26e8669a805f2"; D="https://data-api.polymarket.com"
def get(u): return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0"}),timeout=30).read())
tr=[]
for off in (0,1000,2000,3000,4000):
    p=get("%s/trades?user=%s&limit=1000&offset=%d&takerOnly=false"%(D,A,off))
    if not p: break
    tr+=p
print("trades:",len(tr))
mk=collections.defaultdict(list)
for t in tr: mk[t["conditionId"]].append(t)
print("mercados:",len(mk))
edges=[]; both=0
for cid,ts in mk.items():
    up=[t for t in ts if t["outcomeIndex"]==0]; dn=[t for t in ts if t["outcomeIndex"]==1]
    if up and dn:
        both+=1
        su=sum(t["size"] for t in up); cu=sum(t["size"]*t["price"] for t in up); pu=cu/su
        sd=sum(t["size"] for t in dn); cd=sum(t["size"]*t["price"] for t in dn); pd=cd/sd
        m=min(su,sd); edges.append((1-(pu+pd), m, pu, pd, ts[0]["title"]))
print("mercados com 2 lados:",both)
if edges:
    e=[x[0] for x in edges]
    print("edge combinado (1-(pu+pd)): media=%.3f mediana=%.3f | positivos=%d/%d"%(
        statistics.mean(e),statistics.median(e),sum(1 for x in e if x>0),len(e)))
    print("min=%.3f max=%.3f"%(min(e),max(e)))
    print("\nexemplos:")
    for x in sorted(edges,reverse=True)[:6]:
        print("  edge=%.3f minShare=%.0f pU=%.3f pD=%.3f | %s"%x)
    print("  ...")
    for x in sorted(edges)[:3]:
        print("  edge=%.3f minShare=%.0f pU=%.3f pD=%.3f | %s"%x)
