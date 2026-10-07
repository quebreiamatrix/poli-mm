import net, json, urllib.request
net.install(verbose=False)
def get(u): return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0"}),timeout=30).read())
d=get("https://user-pnl-api.polymarket.com/user-pnl?user_address=0x885ffdf360e5b0b6e6acb963fb3f8ba2344c8ed9&interval=all")
print("forecastication4 primeiros 3:", json.dumps(d[:3]))
print("ultimos 2:", json.dumps(d[-2:]))
print("n=",len(d))
