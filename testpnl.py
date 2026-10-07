import net, json, urllib.request
net.install(verbose=False)
addr="0x885ffdf360e5b0b6e6acb963fb3f8ba2344c8ed9"
def get(u):
    return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0"}),timeout=25).read())
for u in ["https://user-pnl-api.polymarket.com/user-pnl?user_address=%s&interval=all"%addr,
          "https://data-api.polymarket.com/v2/user-pnl?user=%s&interval=all&fidelity=1d"%addr]:
    try:
        d=get(u)
        if isinstance(d,dict) and "points" in d: pts=d["points"]
        else: pts=d
        ps=[(p["t"], p["p"]) for p in pts] if pts and "t" in pts[0] else [(x[0],x[1]) for x in pts]
        fin=float(ps[-1][1])
        peak=-1e18; dd=0
        for t,v in ps:
            v=float(v)
            peak=max(peak,v); dd=max(dd,peak-v)
        print(u.split("?")[0], "| pts=",len(ps),"| final=",round(fin,2),"| MAXDD=",round(dd,2),"| DD%=",round(100*dd/ (fin if fin>0 else 1),1))
    except Exception as e:
        print(u,"ERRO",str(e)[:80])
