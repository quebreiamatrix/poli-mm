import net, json, urllib.request
from collections import Counter
net.install(verbose=False)
RPC="https://polygon.drpc.org"
w="0x41e2e1ccf1e4940029af02259a31c6b89b9fa354"; pad="0x"+"0"*24+w[2:]
def call(method,params):
    body=json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode()
    req=urllib.request.Request(RPC,data=body,headers={"content-type":"application/json","user-agent":"curl/8.0"})
    return json.loads(urllib.request.urlopen(req,timeout=40).read())
bn=int(call("eth_blockNumber",[])["result"],16)
logs=[]
for pos in (2,3):
    r=call("eth_getLogs",[{"fromBlock":hex(bn-45),"toBlock":"latest","topics":[[]]*pos+[pad]}])
    logs+=r.get("result",[])
print("total logs:",len(logs))
c=Counter((l["address"],l["topics"][0],len(l["topics"])) for l in logs)
for k,v in c.most_common(10): print("  addr",k[0],"| sig",k[1][:26],"| ntopics",k[2],"x",v)
# dump um exemplo do principal
main=c.most_common(1)[0][0]
ex=[l for l in logs if l["address"]==main[0] and l["topics"][0]==main[1] and len(l["topics"])==main[2]][0]
print("\nEXEMPLO:")
print(json.dumps(ex,indent=1))
