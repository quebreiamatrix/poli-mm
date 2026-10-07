"""Teste REAL na CLOB: deriva a carteira, checa fundos/aprovacoes e tenta
postar uma ordem ASSINADA. Sem fundos/aprovacao, a CLOB recusa -> isso e' a
realidade que queremos ver. Nada e' assinado com a chave de terceiros.

Chave lida de pk.txt (local) ou env POLY_PK. NAO imprime a chave.
"""
import json
import os
import net

net.install(verbose=False)

from eth_account import Account
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType

HERE = os.path.dirname(os.path.abspath(__file__))
PK = os.environ.get("POLY_PK") or open(os.path.join(HERE, "pk.txt")).read().strip()
if PK.startswith("0x"):
    PK = PK[2:]

acct = Account.from_key(PK)
print("wallet:", acct.address)

HOST = "https://clob.polymarket.com"
CHAIN = 137


def rpc(method, params):
    import urllib.request
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request("https://polygon.drpc.org", data=body,
                                 headers={"content-type": "application/json", "user-agent": "curl/8.0"})
    return json.loads(urllib.request.urlopen(req, timeout=25).read())["result"]


USDC = "0x2791bca1f2de4661ed88a30c99a7a9449aa84174"       # USDC.e (colateral)
EXCH = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"       # CTF Exchange
NEG = "0xC5d563A36AE78145C45a50134d48A1215220f80a"        # NegRisk Exchange

addr = acct.address
matic = int(rpc("eth_getBalance", [addr, "latest"]), 16) / 1e18
bal = int(rpc("eth_call", [{"to": USDC, "data": "0x70a08231" + "0" * 24 + addr[2:]}, "latest"]), 16) / 1e6
print("MATIC: %.4f" % matic)
print("USDC.e: %.4f" % bal)

client = ClobClient(HOST, key=PK, chain_id=CHAIN)
try:
    creds = client.create_or_derive_api_creds()
    client.set_api_creds(creds)
    print("API key derivada OK:", creds.api_key[:8] + "…")
except Exception as e:
    print("creds erro:", e)
    raise SystemExit

# pega um token de mercado ativo
toks = json.loads(net.get_json("https://gamma-api.polymarket.com/events?slug=btc-updown-5m-%d" %
                               (int(__import__("time").time()) // 300 * 300))[0]["markets"][0]["clobTokenIds"])
tok = toks[0]
print("token:", tok[:20], "…")

# ordem BUY 5 shares a 0.01 (bem longe, so pra RESTAR; nao enche)
try:
    args = OrderArgs(price=0.01, size=5, side="BUY", token_id=tok)
    signed = client.create_order(args)
    print("ordem ASSINADA ok. hash:", str(signed.get("hash") if isinstance(signed, dict) else signed)[:24])
    resp = client.post_order(signed, OrderType.GTC)
    print("POST resp:", json.dumps(resp)[:300])
except Exception as e:
    print("POST erro (esperado sem fundos/aprovacao):", str(e)[:300])
