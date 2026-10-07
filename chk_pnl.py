import net, json, urllib.request, time
net.install(verbose=False)
def get(u): return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0"}),timeout=30).read())
rows=json.load(open("miner_top.json"))
for w in rows[:4]:
    d=get("https://user-pnl-api.polymarket.com/user-pnl?user_address=%s&interval=all"%w["addr"])
    pts=[(int(p["t"]),float(p["p"])) for p in d]
    sample=pts[::max(1,len(pts)//8)]
    print("\n%s (%d pts) fin=%.0f"%(w["name"],len(pts),pts[-1][1]))
    print("  ", [ (time.strftime("%m-%d",time.gmtime(t)), round(v)) for t,v in sample ])
    time.sleep(1)
