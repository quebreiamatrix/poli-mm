import net, json, app
net.install(verbose=False)
ev=net.get_json("https://gamma-api.polymarket.com/events?slug=btc-updown-5m-1791306300")[0]["markets"][0]
toks=json.loads(ev["clobTokenIds"]); outs=json.loads(ev["outcomes"])
tokens={toks[i]:outs[i] for i in range(len(toks))}
m=app.mk_market("btc-updown-5m-1791306300","btc",ev["conditionId"],tokens)
# simula 10 shares compradas de cada lado a 0.5 -> caixa -10, custo 10
up=[t for t,o in tokens.items() if o=="Up"][0]
m["inv"][up]=10; m["cash"]=-5.0; m["cost"]=5.0
ok=app.settle_market(m)
print("settle ok:", ok, "| winner:", m.get("winner"), "| pnl:", round(m.get("pnl",0),2))
