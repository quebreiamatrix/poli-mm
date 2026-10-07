import net, json, urllib.request, collections, time
net.install(verbose=False)
A="0x5916ce250c0b3e32eed3303ffb2938cab0b42a0b"; D="https://data-api.polymarket.com"
def get(u):
    for _ in range(3):
        try:
            return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"}),timeout=30).read())
        except Exception:
            time.sleep(0.5)
    return None
act=[]; seen=set(); off=0
while off < 10000:
    p=get("%s/activity?user=%s&limit=100&offset=%d"%(D,A,off))
    if not p: break
    new=0
    for x in p:
        k=(x.get("transactionHash"),x.get("timestamp"),x.get("type"),x.get("size"),x.get("usdcSize"))
        if k in seen: continue
        seen.add(k); act.append(x); new+=1
    if new==0 and off>0: break
    off+=100
print("TOTAL eventos:", len(act), "| por tipo:", dict(collections.Counter(x.get("type") for x in act)))
tr=[x for x in act if x.get("type")=="TRADE"]
print("TRADES:", len(tr), "| por side:", dict(collections.Counter(x.get("side") for x in tr)))
bu=sum(x.get("usdcSize") or 0 for x in tr if x.get("side")=="BUY")
se=sum(x.get("usdcSize") or 0 for x in tr if x.get("side")=="SELL")
sp=sum(x.get("usdcSize") or 0 for x in act if x.get("type")=="SPLIT")
mg=sum(x.get("usdcSize") or 0 for x in act if x.get("type")=="MERGE")
rd=sum(x.get("usdcSize") or 0 for x in act if x.get("type")=="REDEEM")
print("USDC -> BUY=%.0f SELL=%.0f SPLIT=%.0f MERGE=%.0f REDEEM=%.0f"%(bu,se,sp,mg,rd))
print("cashflow (sell+merge+redeem - buy-split) = %.0f"%(se+mg+rd-bu-sp))
json.dump(act, open("anon_act.json","w"))
