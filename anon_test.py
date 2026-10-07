import net, json, urllib.request
net.install(verbose=False)
A="0x5916ce250c0b3e32eed3303ffb2938cab0b42a0b"; pad="0x"+"0"*24+A[2:]
def rpc(m,p):
    b=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode()
    return json.loads(urllib.request.urlopen(urllib.request.Request("https://polygon.drpc.org",data=b,headers={"content-type":"application/json","user-agent":"curl/8.0"}),timeout=25).read())
bn=int(rpc("eth_blockNumber",[])["result"],16)
EX="0xe111180000d2663c0091e4f400237545b87b996b"
for desc,params in [
  ("addr+topics2", {"fromBlock":hex(bn-45),"toBlock":"latest","address":EX,"topics":[[],[],pad]}),
  ("topics2 only", {"fromBlock":hex(bn-45),"toBlock":"latest","topics":[[],[],pad]}),
]:
    r=rpc("eth_getLogs",[params])
    print(desc, "->", ("%d logs"%len(r["result"])) if "result" in r else str(r)[:160])
