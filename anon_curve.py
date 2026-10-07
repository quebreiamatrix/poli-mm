import net, json, urllib.request, time
net.install(verbose=False)
A="0x5916ce250c0b3e32eed3303ffb2938cab0b42a0b"
def get(u): return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"}),timeout=25).read())
for name,u in [("user-pnl-api","https://user-pnl-api.polymarket.com/user-pnl?user_address=%s&interval=all"%A),
               ("v2","https://data-api.polymarket.com/v2/user-pnl?user=%s&interval=all&fidelity=1h"%A)]:
    try:
        d=get(u)
        pts=d if isinstance(d,list) else (d.get("data") or {}).get("points") or []
        vals=[float(p.get("p") if "p" in p else p.get("economic_pnl")) for p in pts]
        print(name,"n=",len(vals),"min=%.0f max=%.0f ini=%.0f fim=%.0f"%(min(vals),max(vals),vals[0],vals[-1]))
    except Exception as e:
        print(name,"ERRO",str(e)[:80])
