import net, json, urllib.request
net.install(verbose=False)
import app
A="0x5916ce250c0b3e32eed3303ffb2938cab0b42a0b"; pad="0x"+"0"*24+A[2:]
def rpc(m,p):
    b=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode()
    return json.loads(urllib.request.urlopen(urllib.request.Request("https://polygon.drpc.org",data=b,headers={"content-type":"application/json","user-agent":"curl/8.0"}),timeout=25).read())
bn=int(rpc("eth_blockNumber",[])["result"],16)
logs=rpc("eth_getLogs",[{"fromBlock":hex(bn-45),"toBlock":"latest","address":"0xe111180000d2663c0091e4f400237545b87b996b","topics":[[],[],pad]}])["result"]
print("logs:",len(logs))
for lg in logs[:3]:
    print("topics2/3:", lg["topics"][2][-8:], lg["topics"][3][-8:], "-> decode:", app._decode_fill(lg, A))
    print("   data words:", app._words(lg["data"])[:5])
