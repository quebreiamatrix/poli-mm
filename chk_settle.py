import net, json
net.install(verbose=False)
for slug in ["btc-updown-5m-1791306300","sol-updown-5m-1791306300"]:
    ev=net.get_json("https://gamma-api.polymarket.com/events?slug=%s"%slug)
    cid=ev[0]["markets"][0]["conditionId"]
    d=net.get_json("https://clob.polymarket.com/markets/%s"%cid)
    win=[t for t in d.get("tokens",[]) if t.get("winner")]
    print(slug, "closed=",d.get("closed"), "winner=", [t["outcome"] for t in win], "prices=", [t.get("price") for t in d.get("tokens",[])])
