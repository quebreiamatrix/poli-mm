import net, json, urllib.request, time, sqlite3
net.install(verbose=False)
A="0x5916ce250c0b3e32eed3303ffb2938cab0b42a0b"; D="https://data-api.polymarket.com"
def get(u): return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"}),timeout=30).read())
# taxa real do Anon (ultimos 1000 trades)
tr=get("%s/trades?user=%s&limit=1000&takerOnly=false"%(D,A))
ts=[t["timestamp"] for t in tr]
span=max(ts)-min(ts)
anon_rate = len(ts)/(span/60) if span else 0
now=int(time.time())
print("ANON: %d trades em %.1f min -> %.2f fills/min (mais novo ha %ds)"%(len(ts),span/60,anon_rate,now-max(ts)))
# nossa taxa no DB
con=sqlite3.connect("pm.db")
la=[r[0] for r in con.execute("select ts from la_fills")]; con.close()
if la:
    sp=max(la)-min(la); our_rate=len(la)/(sp/60) if sp else 0
    print("NOS: %d fills em %.1f min -> %.2f fills/min"%(len(la),sp/60,our_rate))
    print("FATOR (anon/nos) = %.4f  -> haircut ~%.1f%%"%(anon_rate/our_rate if our_rate else 0, 100*anon_rate/our_rate if our_rate else 0))
