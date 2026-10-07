import net, json, urllib.request
net.install(verbose=False)
w="0x41e2e1ccf1e4940029af02259a31c6b89b9fa354"; pad="0x"+"0"*24+w[2:]
rpcs=["https://polygon-bor-rpc.publicnode.com","https://polygon-mainnet.public.blastapi.io",
      "https://polygon.api.onfinality.io/public","https://rpc.polygon.gateway.fm",
      "https://polygon.blockpi.network/v1/rpc/public","https://polygon.rpc.blxrbdn.com",
      "https://polygon.drpc.org"]
def call(rpc,method,params):
    body=json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode()
    req=urllib.request.Request(rpc,data=body,headers={"content-type":"application/json","user-agent":"curl/8.0"})
    try: return json.loads(urllib.request.urlopen(req,timeout=25).read())
    except urllib.error.HTTPError as e: return {"http":e.code,"body":e.read().decode()[:150]}
    except Exception as e: return {"err":str(e)[:120]}
for rpc in rpcs:
    bn=call(rpc,"eth_blockNumber",[])
    if "result" not in bn: print(rpc,"-> blockNumber FAIL",str(bn)[:110]); continue
    b=int(bn["result"],16)
    r=call(rpc,"eth_getLogs",[{"fromBlock":hex(b-50),"toBlock":"latest","topics":[[],[],[pad]]}])
    ok = "result" in r
    print(rpc,"-> block %d | getLogs %s"%(b, ("%d logs"%len(r["result"])) if ok else "FAIL "+str(r)[:100]))
