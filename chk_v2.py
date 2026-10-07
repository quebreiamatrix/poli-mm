import net, json, urllib.request
net.install(verbose=False)
def raw(u):
    try:
        return urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"}),timeout=25).read().decode()
    except urllib.error.HTTPError as e:
        return "HTTP %d: %s"%(e.code,e.read().decode()[:200])
for a in ["0xed2239a915b4d3b8a6b4f1b0a0c0c0c0c0c0c0c0","0x885ffdf360e5b0b6e6acb963fb3f8ba2344c8ed9"]:
    for q in ["v2/user-pnl?user=%s&interval=all&fidelity=1d","v2/user-pnl?user=%s&interval=max&fidelity=1d"]:
        print(q.split('?')[0], a[:10], "->", raw("https://data-api.polymarket.com/"+q%a)[:180])
