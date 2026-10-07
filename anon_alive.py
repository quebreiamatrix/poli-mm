import net, json, urllib.request, time
net.install(verbose=False)
A="0x5916ce250c0b3e32eed3303ffb2938cab0b42a0b"; D="https://data-api.polymarket.com"
def get(u): return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"}),timeout=30).read())
now=int(time.time())
tr=get("%s/trades?user=%s&limit=10&takerOnly=false"%(D,A))
print("ultimos trades do Anon (idade):", [now-t["timestamp"] for t in tr[:6]])
act=get("%s/activity?user=%s&limit=10"%(D,A))
print("ultimas atividades (idade, tipo):", [(now-a["timestamp"], a["type"]) for a in act[:6]])
