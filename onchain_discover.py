import net, json, urllib.request
net.install(verbose=False)
RPC="https://polygon.drpc.org"
w="0x41e2e1ccf1e4940029af02259a31c6b89b9fa354"; pad="0x"+"0"*24+w[2:]
def call(method,params):
    body=json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode()
    req=urllib.request.Request(RPC,data=body,headers={"content-type":"application/json","user-agent":"curl/8.0"})
    try: return json.loads(urllib.request.urlopen(req,timeout=40).read())
    except urllib.error.HTTPError as e: return {"http":e.code,"body":e.read().decode()[:200]}
bn=int(call("eth_blockNumber",[])["result"],16)
from collections import Counter
for rng in (900,500,200):
    r=call("eth_getLogs",[{"fromBlock":hex(bn-rng),"toBlock":"latest","topics":[[],[],[pad]]}])
    print("range",rng,"->",str(r)[:180] if "result" not in r else ("%d logs"%len(r["result"])))
    if "result" in r:
        c=Counter((l["address"],l["topics"][0]) for l in r["result"])
        for k,v in c.most_common(8): print("    addr",k[0],"sig",k[1][:24],"x",v)
        break
