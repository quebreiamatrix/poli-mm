import net, json, urllib.request
net.install(verbose=False)
w="0x41e2e1ccf1e4940029af02259a31c6b89b9fa354"
pad="0x"+"0"*24+w[2:]
def call(rpc,method,params):
    body=json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode()
    req=urllib.request.Request(rpc,data=body,headers={"content-type":"application/json","user-agent":"curl/8.0"})
    try:
        return json.loads(urllib.request.urlopen(req,timeout=30).read())
    except urllib.error.HTTPError as e:
        return {"http_error":e.code,"body":e.read().decode()[:300]}
for rpc in ["https://polygon.drpc.org","https://1rpc.io/matic","https://polygon.llamarpc.com"]:
    bn=call(rpc,"eth_blockNumber",[])
    print(rpc,"blockNumber ->",str(bn)[:120])
    logs=call(rpc,"eth_getLogs",[{"fromBlock":"0x5aa0000","toBlock":"latest","topics":[None,None,pad]}])
    print("   getLogs ->",str(logs)[:200])
