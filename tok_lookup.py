import net, json
net.install(verbose=False)
tok="110761796201558894745680964557098081494556551885156666561541512767817677911414"
for url in [
  "https://gamma-api.polymarket.com/markets?clob_token_ids=%s"%tok,
  "https://gamma-api.polymarket.com/markets?clob_token_id=%s"%tok,
  "https://gamma-api.polymarket.com/markets?clobTokenIds=%s"%tok,
]:
    try:
        r=net.get_json(url,tries=1)
        print(url.split("markets?")[1][:30], "->", ("%d"%len(r)) if isinstance(r,list) else str(r)[:80])
        if isinstance(r,list) and r: print("    ", r[0].get("slug"), r[0].get("outcomes"), r[0].get("conditionId")[:12])
    except Exception as e:
        print(url.split("markets?")[1][:30],"ERRO",str(e)[:60])
