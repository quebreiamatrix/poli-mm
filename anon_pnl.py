import json, collections, statistics
act=json.load(open("anon_act.json"))
mk=collections.defaultdict(lambda: {"buy":0,"sell":0,"split":0,"merge":0,"redeem":0,"n":0})
for x in act:
    cid=x.get("conditionId") or "?"; m=mk[cid]; m["n"]+=1
    u=x.get("usdcSize") or 0
    t=x.get("type")
    if t=="TRADE" and x.get("side")=="BUY": m["buy"]+=u
    elif t=="TRADE" and x.get("side")=="SELL": m["sell"]+=u
    elif t=="SPLIT": m["split"]+=u
    elif t=="MERGE": m["merge"]+=u
    elif t=="REDEEM": m["redeem"]+=u
rows=[]
for cid,m in mk.items():
    net=m["sell"]+m["merge"]+m["redeem"]-m["buy"]-m["split"]
    rows.append((net,cid,m["n"],m["split"],m["sell"],m["merge"],m["redeem"]))
rows.sort(reverse=True)
tot=sum(r[0] for r in rows)
print("mercados distintos:",len(rows),"| PnL liquido total (cashflow): %.0f"%tot)
print("positivos: %d | negativos: %d"%(sum(1 for r in rows if r[0]>0),sum(1 for r in rows if r[0]<0)))
nz=[r[0] for r in rows]
print("por mercado: medi=%.1f mediana=%.1f maior=%.0f menor=%.0f"%(statistics.mean(nz),statistics.median(nz),max(nz),min(nz)))
print("\nTOP 8 (lucro) / BOTTOM 4 (perda): net | split | sell | merge | redeem")
for r in rows[:8]+rows[-4:]:
    print("  %+8.0f | split=%7.0f sell=%6.0f merge=%7.0f redeem=%7.0f"%(r[0],r[3],r[4],r[5],r[6]))
