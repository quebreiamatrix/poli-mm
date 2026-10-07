import net, json
net.install(verbose=False)
for slug in ["btc-updown-5m-1791306300","btc-updown-5m-1791306000"]:
    ev=net.get_json("https://gamma-api.polymarket.com/events?slug=%s"%slug)
    m=ev[0]["markets"][0]
    print(slug, "closed=",m.get("closed"),"uma=",m.get("umaResolutionStatus"),"outcomes=",m.get("outcomes"),"prices=",m.get("outcomePrices"))
