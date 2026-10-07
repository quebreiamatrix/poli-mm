"""Assinador REAL de ordens da CLOB (Polymarket).

A cada entrada do nosso bot, construimos e ASSINAMOS a ordem de verdade
(EIP-712) com a carteira de pk.txt/env POLY_PK — igual a uma ordem que iria
pro livro. Por padrao NAO envia (POST), porque o IP desta maquina esta
geobloqueado (403). Ligue POLY_POST=1 quando estiver num IP permitido.

NAO imprime a chave.
"""
import os

import net

try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import OrderArgs, OrderType
    HAVE = True
except Exception:
    HAVE = False

HOST = "https://clob.polymarket.com"
CHAIN = 137

_state = {"init": False, "client": None, "err": None}


def _init():
    if _state["init"]:
        return
    _state["init"] = True
    if not HAVE:
        _state["err"] = "py_clob_client ausente"
        return
    here = os.path.dirname(os.path.abspath(__file__))
    pk = os.environ.get("POLY_PK")
    if not pk:
        p = os.path.join(here, "pk.txt")
        if os.path.exists(p):
            pk = open(p).read().strip()
    if not pk:
        _state["err"] = "sem chave (pk.txt / POLY_PK)"
        return
    if pk.startswith("0x"):
        pk = pk[2:]
    try:
        c = ClobClient(HOST, key=pk, chain_id=CHAIN)
        c.set_api_creds(c.create_or_derive_api_creds())
        _state["client"] = c
    except Exception as e:
        _state["err"] = str(e)[:120]


def wallet():
    _init()
    try:
        from eth_account import Account
        here = os.path.dirname(os.path.abspath(__file__))
        pk = os.environ.get("POLY_PK") or open(os.path.join(here, "pk.txt")).read().strip()
        return Account.from_key(pk).address
    except Exception:
        return None


def _dig(obj, keys):
    """Procura um campo em objeto/dict/pydantic."""
    if obj is None:
        return None
    for k in keys:
        v = getattr(obj, k, None)
        if v:
            return str(v)
    if hasattr(obj, "dict"):
        try:
            d = obj.dict()
            for k in keys:
                if isinstance(d, dict) and d.get(k):
                    return str(d[k])
        except Exception:
            pass
    return None


def _fields(s):
    """Extrai hash e assinatura de um SignedOrder de qualquer formato."""
    h = _dig(s, ["hash", "orderHash", "order_hash"])
    if not h:
        h = _dig(getattr(s, "order", None), ["hash", "orderHash", "order_hash"])
    sig = _dig(s, ["signature", "sig"])
    return h, sig


def sign(token_id, side, price, size):
    """Assina a ordem real. Retorna {'hash','sig'} ou {'err'}."""
    _init()
    c = _state["client"]
    if c is None:
        return {"err": _state["err"] or "sem assinante"}
    try:
        args = OrderArgs(price=round(float(price), 2) or 0.01,
                         size=round(float(size), 2),
                         side=side, token_id=str(token_id))
        s = c.create_order(args)
        h, sig = _fields(s)
        out = {"hash": (h or "")[:26], "sig": (sig or "")[:18]}
        if os.environ.get("POLY_POST") == "1":
            try:
                out["post"] = str(c.post_order(s, OrderType.GTC))[:140]
            except Exception as e:
                out["post_err"] = str(e)[:140]
        _state["last"] = out
        return out
    except Exception as e:
        out = {"err": str(e)[:120]}
        _state["last"] = out
        return out
