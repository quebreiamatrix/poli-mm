import net, time
net.install(verbose=False)
now=int(time.time())
tr=net.get_json("https://data-api.polymarket.com/trades?user=0x41e2e1ccf1e4940029af02259a31c6b89b9fa354&limit=20")
ts=[t["timestamp"] for t in tr]
print("now=%d | newest trade ha %ds (%.1f min) | n=%d"%(now, now-max(ts), (now-max(ts))/60, len(tr)))
for t in tr[:5]:
    print("  ha %ds : %s %s %s @%s"%(now-t["timestamp"], t["slug"].split("-")[0], t["outcome"], t["side"], t["price"]))
