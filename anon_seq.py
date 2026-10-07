import net, json, urllib.request, collections
net.install(verbose=False)
A="0x5916ce250c0b3e32eed3303ffb2938cab0b42a0b"; D="https://data-api.polymarket.com"
def get(u): return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"}),timeout=30).read())
act=[]
for off in (0,500,1000):
    a=get("%s/activity?user=%s&limit=500&offset=%d"%(D,A,off))
    if not a: break
    act+=a
print("eventos:",len(act), collections.Counter(x["type"] for x in act))
# escolhe um mercado com SPLIT e varios SELL
byc=collections.defaultdict(list)
for x in act: byc[x.get("conditionId","")].append(x)
cand=max(byc.items(), key=lambda kv: sum(1 for x in kv[1] if x["type"]=="SPLIT"))
cid,xs=cand
xs=sorted(xs,key=lambda x:x.get("timestamp") or 0)
print("\nmercado:", xs[0].get("title"))
print("eventos nesse mercado:", collections.Counter(x["type"] for x in xs))
sell=sum(x["usdcSize"] for x in xs if x["type"]=="TRADE" and x["side"]=="SELL")
buy=sum(x["usdcSize"] for x in xs if x["type"]=="TRADE" and x["side"]=="BUY")
sp=sum(x["usdcSize"] for x in xs if x["type"]=="SPLIT"); mg=sum(x["usdcSize"] for x in xs if x["type"]=="MERGE"); rd=sum(x["usdcSize"] for x in xs if x["type"]=="REDEEM")
print("SELL=%.0f BUY=%.0f SPLIT=%.0f MERGE=%.0f REDEEM=%.0f"%(sell,buy,sp,mg,rd))
print("\nsequencia (primeiras 18):")
for x in xs[:18]:
    print("  t+%5ds %-7s %-5s sz=%-8.1f usdc=%-8.1f p=%.2f %s"%(x["timestamp"]-xs[0]["timestamp"],x["type"],x.get("side") or "",x.get("size") or 0,x.get("usdcSize") or 0,x.get("price") or 0,(x.get("outcome") or "")[:5]))
