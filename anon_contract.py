import net, json, urllib.request
net.install(verbose=False)
A="0x5916ce250c0b3e32eed3303ffb2938cab0b42a0b"; pad="0x"+"0"*24+A[2:]
def rpc(m,p):
    b=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode()
    return json.loads(urllib.request.urlopen(urllib.request.Request("https://polygon.drpc.org",data=b,headers={"content-type":"application/json","user-agent":"curl/8.0"}),timeout=25).read())["result"]
bn=int(rpc("eth_blockNumber",[]),16)
from collections import Counter
for pos in (2,3):
    logs=rpc("eth_getLogs",[{"fromBlock":hex(bn-45),"toBlock":"latest","topics":[[]]*pos+[pad]}])
    print("pos",pos,"logs",len(logs), Counter((l["address"],l["topics"][0][:20]) for l in logs).most_common(4))
