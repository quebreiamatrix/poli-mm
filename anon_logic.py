import net, json, urllib.request, collections, statistics, time
net.install(verbose=False)
A="0x5916ce250c0b3e32eed3303ffb2938cab0b42a0b"; D="https://data-api.polymarket.com"
def get(u): return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"}),timeout=30).read())
tr=[]
for off in (0,1000,2000,3000):
    p=get("%s/trades?user=%s&limit=1000&offset=%d&takerOnly=false"%(D,A,off))
    if not p: break
    tr+=p
print("trades:",len(tr))
now=int(time.time()); ts=[t["timestamp"] for t in tr]
print("janela %.1f min | ultimo ha %ds" % ((max(ts)-min(ts))/60, now-max(ts)))
print("sides:", collections.Counter(t["side"] for t in tr))
print("precos:", collections.Counter(round(t["price"],2) for t in tr).most_common(10))
print("sizes:", collections.Counter(round(t["size"],0) for t in tr).most_common(10))
print("mercados:", collections.Counter(t["title"][:38] for t in tr).most_common(6))
print("atividade:", collections.Counter(a.get("type") for a in get("%s/activity?user=%s&limit=500"%(D,A))))
mk=collections.defaultdict(list)
for t in tr: mk[t["conditionId"]].append(t)
edges=[]
for cid,x in mk.items():
    u=[t for t in x if t["outcomeIndex"]==0]; d=[t for t in x if t["outcomeIndex"]==1]
    if u and d:
        su=sum(t["size"] for t in u); pu=sum(t["size"]*t["price"] for t in u)/su
        sd=sum(t["size"] for t in d); pd=sum(t["size"]*t["price"] for t in d)/sd
        edges.append((1-(pu+pd), min(su,sd), pu, pd, x[0]["title"]))
print("\nmercados com 2 lados:",len(edges))
if edges:
    e=[x[0] for x in edges]
    print("edge combinado: mediana=%.3f media=%.3f positivos=%d/%d"%(statistics.median(e),statistics.mean(e),sum(1 for x in e if x>0),len(e)))
    for x in sorted(edges,reverse=True)[:5]: print("  edge=%.3f minSz=%.0f pU=%.3f pD=%.3f | %s"%(x[0],x[1],x[2],x[3],x[4][:36]))
