import net, json, urllib.request, time
net.install(verbose=False)
A="0x5916ce250c0b3e32eed3303ffb2938cab0b42a0b"
for url in ["https://data-api.polymarket.com/trades?user=%s&limit=100&takerOnly=false"%A,
            "https://data-api.polymarket.com/trades?user=%s&limit=100"%A]:
    try:
        d=json.loads(urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"}),timeout=25).read())
        now=int(time.time())
        print(url.split("trades?")[1][:40], "-> n=",len(d), "newest_age=", now-d[0]["timestamp"])
    except Exception as e:
        print(url[:60],"ERRO",str(e)[:80])
