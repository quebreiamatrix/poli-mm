import net, json, urllib.request
net.install(verbose=False)
def get(u): return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"}),timeout=25).read())
d=get("https://data-api.polymarket.com/v2/user-pnl?user=0x885ffdf360e5b0b6e6acb963fb3f8ba2344c8ed9&interval=all&fidelity=1d")
pts=d["data"]["points"]
print("n=",len(pts))
print("primeiro:",json.dumps(pts[0]))
print("ultimo:",json.dumps(pts[-1]))
