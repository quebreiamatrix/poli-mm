import net, json, urllib.request, time, collections
net.install(verbose=False)
A="0xd9e0aaca471f489be338fd0f91a26e8669a805f2"; D="https://data-api.polymarket.com"
def get(u): 
    return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"}),timeout=30).read())
tr=get("%s/trades?user=%s&limit=1000&takerOnly=false"%(D,A))
print("trades:",len(tr))
now=int(time.time()); ts=[t["timestamp"] for t in tr]
print("janela: %.1f min" % ((max(ts)-min(ts))/60), "| mais novo ha %ds"%(now-max(ts)))
print("sides:", collections.Counter(t["side"] for t in tr))
print("precos:", collections.Counter(round(t["price"],2) for t in tr).most_common(8))
print("sizes:", collections.Counter(round(t["size"],1) for t in tr).most_common(8))
mk=collections.Counter(t["title"] for t in tr)
print("\ntop mercados:")
for k,v in mk.most_common(8): print("  %3d  %s"%(v,k))
print("\ntipos de atividade (ult 500):")
act=get("%s/activity?user=%s&limit=500"%(D,A))
print("  ", collections.Counter(a.get("type") for a in act))
# um mercado: ver se opera os dois lados
import re
t0=tr[0]["conditionId"]
sub=[t for t in tr if t["conditionId"]==t0]
print("\nmercado exemplo:",tr[0]["title"],"| trades:",len(sub))
print("  outcomes:", collections.Counter(t["outcome"] for t in sub), "| sides:", collections.Counter(t["side"] for t in sub))
