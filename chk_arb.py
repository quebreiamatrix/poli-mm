import net, json, time
net.install(verbose=False)
w=int(time.time())//300*300
ev=net.get_json("https://gamma-api.polymarket.com/events?slug=btc-updown-5m-%d"%w)[0]["markets"][0]
toks=json.loads(ev["clobTokenIds"]); outs=json.loads(ev["outcomes"])
print("market:", ev["slug"], outs)
for i,t in enumerate(toks):
    bk=net.get_json("https://clob.polymarket.com/book?token_id=%s"%t)
    bids=sorted([float(b["price"]) for b in bk.get("bids",[]) if float(b["size"])>0],reverse=True)
    asks=sorted([float(a["price"]) for a in bk.get("asks",[]) if float(a["size"])>0])
    bb=bids[0] if bids else None; ba=asks[0] if asks else None
    print("  %-5s token %s… bb=%s ba=%s (#bids=%d #asks=%d)"%(outs[i], t[:10], bb, ba, len(bids), len(asks)))
# soma dos dois lados
allb=[]
for t in toks:
    bk=net.get_json("https://clob.polymarket.com/book?token_id=%s"%t)
    allb.append(bk)
def bid(bk):
    b=[float(x["price"]) for x in bk.get("bids",[]) if float(x["size"])>0]; return max(b) if b else None
def ask(bk):
    a=[float(x["price"]) for x in bk.get("asks",[]) if float(x["size"])>0]; return min(a) if a else None
bb=[bid(x) for x in allb]; ba=[ask(x) for x in allb]
print("Σbid = %s | Σask = %s"%(bb[0]+bb[1] if all(bb) else None, ba[0]+ba[1] if all(ba) else None))
