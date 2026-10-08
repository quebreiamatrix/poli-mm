"""poli-mm — Shadow market maker (DRY) nos mercados Up/Down de 5 min.

Objetivo: reproduzir a logica observada na carteira norm1e69 —
  cota bids nos DOIS outcomes em torno do preco justo, e preenchido por
  takers, mantem o livro ~neutro e carrega ate a liquidacao, capturando o
  spread (~2-3%).

NAO envia ordem nenhuma. Le o WebSocket de mercado REAL da CLOB (livro +
trades) e simula os nossos fills. Banca/risco aqui sao so medicao.

Fonte: wss://ws-subscriptions-clob.polymarket.com/ws/market
  - book             -> snapshot L2
  - price_change     -> atualiza best_bid/best_ask
  - last_trade_price -> trade real (side = lado do AGRESSOR)

Fill: cotamos bid no best_bid. Quando um trade SELL imprime <= nosso bid,
caimos -> fill no nosso preco.

Rode:  python app.py     ->  http://localhost:8800
"""
import asyncio
import json
import os
import queue
import threading
import time
import traceback
import urllib.request
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    import orjson as _orjson

    def _loads(s):
        if isinstance(s, (bytes, bytearray, memoryview)):
            return _orjson.loads(s)
        return _orjson.loads(str(s).encode("utf-8", "ignore"))

    JSON_FAST = True
except Exception:
    def _loads(s):
        return json.loads(s)

    JSON_FAST = False

import net
import clob_signer
import db

# ----------------------------- config -----------------------------
ASSETS = ["btc", "eth", "sol"]
DURATION = "5m"
DUR_SEC = 300
LATENCY_MS = 300          # nosso quote so fica "no livro" depois disso
TICK = 0.01
QUOTE_SIZE = 10           # shares por ordem
MAX_USD_PER_TOKEN = 80.0  # teto de exposicao por token -> 6 tokens ~ $480 (48% de $1k)
BANCA = 1000.0            # banca simulada (USDC)
MIN_MID, MAX_MID = 0.15, 0.85   # so cota em mercado "vivo" (nao decidido)
HTTP_PORT = 8800
WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

TARGET_WALLET = {
    "name": "norm1e69",
    "address": "0x41e2e1ccf1e4940029af02259a31c6b89b9fa354",
    "edge": 0.0246, "winrate": 0.597,
}

ANON_ADDR = "0x5916ce250c0b3e32eed3303ffb2938cab0b42a0b"
LA_ORD = 30               # tamanho da nossa ordem (ask) — min 5 shares
LA_MAX_PER_TOKEN = 1500
LA_NET_CAP = 5
LA_BANCA = 100.0
LA_USD = 75.0
HAIRCUT = 1.0             # FIFO ja e a calibracao; haircut extra opcional

# --- ARB 100% neutro (aba nova) ---
ARB_SIZE = 10             # shares por perna do par
ARB_THETA = 0.07          # taker fee (crypto): fee = theta * C * p * (1-p)
ARB_MARGIN = 0.0          # lucro minimo exigido (apos taxas) por par
ARB_COOLDOWN = 5          # s entre disparos no mesmo mercado
MATCH_WINDOW_S = 20        # "entramos junto" = fill nosso na mesma moeda em +/- 20s

# --- feed on-chain em tempo real da carteira alvo ---
POLY_RPC = "https://polygon.drpc.org"
EXCHANGE = "0xe111180000d2663c0091e4f400237545b87b996b"
ORDERFILL_TOPIC = "0xd543adfd945773f1a62f74f0ee55a5e3b9b1a28262980ba90b1a89f2ea84d8ee"
TARGET_TOPIC = "0x" + "0" * 24 + TARGET_WALLET["address"][2:].lower()
ANON_TOPIC = "0x" + "0" * 24 + ANON_ADDR[2:].lower()

# curva historica do alvo (gerada por gen_hist.py)
try:
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "target_history.json"), encoding="utf-8") as _f:
        TARGET_HIST = json.load(_f)
except Exception:
    TARGET_HIST = {"equity": [], "pnl": 0, "markets": 0, "roi": 0, "title": "sem historico"}

LOCK = threading.Lock()
MSGQ = queue.Queue()          # fila: reader (WS) -> processor (thread separada)
TOK2M = {}                    # token_id -> market da janela corrente
WS_LAST_MSG = 0.0             # timestamp da ultima mensagem WS recebida
WS_RECONNECTS = 0             # reconexoes do WS nesta sessao
WS_DROPPED = 0                # mensagens antigas descartadas da fila em sobrecarga
STATE = {
    "started": time.time(), "mode": "DRY (sem ordens)", "latency_ms": LATENCY_MS,
    "quote_size": QUOTE_SIZE, "ws": "desconectado", "books_seen": 0, "trades_seen": 0,
    "markets": {}, "settled": [],
    "recent_trades": [],
    "target_trades": [],
    "target_fills": [],          # fills on-chain em tempo real do alvo
    "pnl_series": [],            # [(epoch, pnl_total)] amostrado ao vivo
    "onchain": {"last_block": 0, "events": 0, "err": ""},
    "mirror": {"n": 0, "slip_sum": 0.0, "late_sum": 0.0},
    "arb": {"pnl": 0.0, "sets": 0, "buy": 0, "sell": 0, "events": [], "last_opp": 0},
    "peak_open": 0.0,            # maior exposicao (USDC) ja empregada
    "la_peak": 0.0,              # maior capital aberto do LikeAnon
    "anon": {"trades": [], "sell_usdc": 0.0, "split": 0.0, "merge": 0.0, "redeem": 0.0,
             "pnl_total": 0.0, "day_pnl": 0.0, "curves": {}, "err": "",
             "fills": [], "oc": {"last_block": 0, "events": 0, "err": ""}},
    "la_settled": [],
    "totals": {"cost": 0.0, "payout": 0.0, "pnl": 0.0, "fills": 0, "markets": 0,
               "wins": 0, "losses": 0, "spread_captured": 0.0, "shares_filled": 0.0},
    "errors": [],
}


def _open_locked():
    """PnL em aberto (marcado a mercado). Requer LOCK ja adquirido."""
    op = 0.0
    for m in STATE["markets"].values():
        val = m["cash"]
        for tk, pos in m["inv"].items():
            mid = (m["books"].get(tk) or {}).get("mid")
            if mid is not None:
                val += pos * mid
        op += val
    return op


def sampler():
    """Amostra o PnL total (realizado + aberto) a cada 5s p/ o grafico ao vivo."""
    while True:
        time.sleep(5)
        try:
            with LOCK:
                v = STATE["totals"]["pnl"] + _open_locked()
                STATE["pnl_series"].append([int(time.time()), round(v, 2)])
                STATE["pnl_series"] = STATE["pnl_series"][-3000:]
                oc = sum(m["cost"] for m in STATE["markets"].values())
                if oc > STATE["peak_open"]:
                    STATE["peak_open"] = oc
                la_open = -sum(m["la"]["cash"] for m in STATE["markets"].values())
                if la_open > STATE["la_peak"]:
                    STATE["la_peak"] = la_open
                # selecao adversa: mid ~30s apos cada venda (vender barato = mid subiu)
                nowt = int(time.time())
                for m in STATE["markets"].values():
                    for f in m["la"]["fills"]:
                        if f.get("adv") is None and nowt - f["ts"] >= 30:
                            mn = (m["books"].get(f["token"]) or {}).get("mid")
                            if mn is not None:
                                f["adv"] = round(mn - f["price"], 5)
        except Exception:
            pass


def log_err(msg):
    with LOCK:
        STATE["errors"].append("%s %s" % (time.strftime("%H:%M:%S"), msg))
        STATE["errors"] = STATE["errors"][-20:]


def mk_market(slug, asset, cid, tokens):
    return {"slug": slug, "asset": asset, "cid": cid, "tokens": tokens,
            "start": int(slug.rsplit("-", 1)[1]),
            "end": int(slug.rsplit("-", 1)[1]) + DUR_SEC,
            "books": {}, "quotes": {}, "inv": defaultdict(float), "cost": 0.0, "cash": 0.0,
            "fills": [], "settled": False, "winner": None, "pnl": 0.0, "active": True,
            "trades": 0, "sell_trades": 0,
            # --- LikeAnon: vende (ask) e capta estoque via SPLIT ---
            "la": {"inv": defaultdict(float), "sold": defaultdict(float), "cash": 0.0,
                   "split": 0.0, "fills": [], "pnl": 0.0, "merged": 0.0, "redeemed": 0.0}}


def discover(w):
    out = []
    for a in ASSETS:
        slug = "%s-updown-5m-%d" % (a, w)
        try:
            ev = net.get_json("https://gamma-api.polymarket.com/events?slug=%s" % slug, tries=2)
            if not ev:
                continue
            m = ev[0]["markets"][0]
            toks = json.loads(m["clobTokenIds"]); outs = json.loads(m["outcomes"])
            out.append((slug, a, m["conditionId"], {toks[i]: outs[i] for i in range(len(toks))}))
        except Exception as e:
            log_err("discover %s: %s" % (slug, e))
    return out


def register(slug, asset, cid, tokens):
    with LOCK:
        if slug not in STATE["markets"]:
            m = mk_market(slug, asset, cid, tokens)
            STATE["markets"][slug] = m
            up = next((k for k, v in tokens.items() if v == "Up"), "")
            dn = next((k for k, v in tokens.items() if v == "Down"), "")
            db.market(slug, asset, cid, up, dn, m["start"], m["end"])
        return STATE["markets"][slug]


def on_book(m, ev):
    tok = ev["asset_id"]
    bids = [(float(b["price"]), float(b["size"])) for b in ev.get("bids", []) if float(b["size"]) > 0]
    asks = [(float(a["price"]), float(a["size"])) for a in ev.get("asks", []) if float(a["size"]) > 0]
    bb = max(bids, key=lambda x: x[0]) if bids else None
    ba = min(asks, key=lambda x: x[0]) if asks else None
    m["books"][tok] = {
        "bb": bb[0] if bb else None, "bb_sz": bb[1] if bb else 0,
        "ba": ba[0] if ba else None, "ba_sz": ba[1] if ba else 0,
        "mid": ((bb[0] + ba[0]) / 2) if (bb and ba) else (bb[0] if bb else (ba[0] if ba else None)),
    }
    STATE["books_seen"] += 1
    db.tick(tok, m["books"][tok].get("bb"), m["books"][tok].get("ba"),
            m["books"][tok].get("bb_sz"), m["books"][tok].get("ba_sz"))
    quote(m, tok)
    arb_check(m, time.time())


def on_price_change(m, ev):
    touched = set()
    for c in ev.get("price_changes", []):
        tok = c["asset_id"]
        if tok not in m["tokens"]:
            continue
        b = m["books"].get(tok)
        if b is None:
            b = m["books"][tok] = {}
        if c.get("best_bid"):
            b["bb"] = float(c["best_bid"])
        if c.get("best_ask"):
            b["ba"] = float(c["best_ask"])
        if b.get("bb") is not None and b.get("ba") is not None:
            b["mid"] = (b["bb"] + b["ba"]) / 2
        touched.add(tok)
    STATE["books_seen"] += len(touched)
    for tok in touched:
        quote(m, tok)
    arb_check(m, time.time())


def quote(m, tok):
    """Cotacao BILATERAL: bid no best_bid e ask no best_ask (sem banda, cobre extremos)."""
    b = m["books"].get(tok, {})
    bb, ba = b.get("bb"), b.get("ba")
    if bb is None or ba is None:
        m["quotes"].pop(tok, None)
        return
    bid = min(1 - TICK, max(TICK, round(bb / TICK) * TICK))
    ask = min(1 - TICK, max(TICK, round(ba / TICK) * TICK))
    if bid >= ask:
        return
    q = m["quotes"].get(tok)
    if (not q or abs(q["bid"]["price"] - bid) > 1e-9 or abs(q["ask"]["price"] - ask) > 1e-9):
        aa = time.time() + LATENCY_MS / 1000.0
        # fila REAL: tamanho do nivel (sem cap) — FIFO de verdade
        m["quotes"][tok] = {"bid": {"price": bid, "active_at": aa, "ahead": float(b.get("bb_sz") or 0)},
                            "ask": {"price": ask, "active_at": aa, "ahead": float(b.get("ba_sz") or 0)}}


def arb_check(m, now):
    """ARB 100% neutro: compra o PAR se Sum(ask)<1, ou vende o PAR se Sum(bid)>1 — sempre as duas pernas juntas."""
    if now - m.get("arb_last", 0) < ARB_COOLDOWN:
        return
    up = dn = None
    for tk, out in m["tokens"].items():
        if out == "Up":
            up = tk
        elif out == "Down":
            dn = tk
    if not up or not dn:
        return
    bu = m["books"].get(up) or {}
    bd = m["books"].get(dn) or {}
    aU, aD = bu.get("ba"), bd.get("ba")     # ask: o que pagamos p/ comprar
    bU, bD = bu.get("bb"), bd.get("bb")     # bid: o que recebemos ao vender

    def fee(p):
        return ARB_THETA * ARB_SIZE * p * (1 - p)

    if aU and aD:
        prof = 1.0 - (aU + aD) - (fee(aU) + fee(aD))
        if prof > ARB_MARGIN:
            m["arb_last"] = now
            with LOCK:
                a = STATE["arb"]
                a["pnl"] += round(prof, 4); a["sets"] += 1; a["buy"] += 1
                a["events"].insert(0, {"ts": int(now), "asset": m["asset"].upper(),
                                       "side": "BUY par", "combo": round(aU + aD, 4), "profit": round(prof, 4)})
                a["events"] = a["events"][:60]
            return
    if bU and bD:
        prof = (bU + bD) - 1.0 - (fee(bU) + fee(bD))
        if prof > ARB_MARGIN:
            m["arb_last"] = now
            with LOCK:
                a = STATE["arb"]
                a["pnl"] += round(prof, 4); a["sets"] += 1; a["sell"] += 1
                a["events"].insert(0, {"ts": int(now), "asset": m["asset"].upper(),
                                       "side": "SELL par", "combo": round(bU + bD, 4), "profit": round(prof, 4)})
                a["events"] = a["events"][:60]


def on_trade(m, ev):
    tok = ev["asset_id"]
    if tok not in m["tokens"]:
        return
    price = float(ev["price"]); size = float(ev["size"]); side = ev.get("side")
    m["trades"] += 1
    if side == "SELL":
        m["sell_trades"] += 1
    with LOCK:
        STATE["trades_seen"] += 1
        STATE["recent_trades"].insert(0, {
            "t": int(time.time()), "asset": m["asset"], "outcome": m["tokens"][tok],
            "side": side, "price": price, "size": size})
        STATE["recent_trades"] = STATE["recent_trades"][:40]
    _ts = int(ev.get("timestamp") or time.time() * 1000)
    if _ts > 10 ** 12:
        _ts //= 1000
    db.trade(_ts, tok, m["cid"], price, size, side, ev.get("transaction_hash"))

    # fila bilateral: compra se alguem VENDEU no nosso bid; vende se alguem COMPROU no nosso ask
    q = m["quotes"].get(tok)
    if not q:
        return
    now = time.time()
    b = m["books"].get(tok, {})
    mid = b.get("mid") or price
    # ---- LikeAnon: vende no ask; capta estoque via SPLIT ($1/par) quando faltar ----
    if side == "BUY":
        la = m["la"]
        pr = q["ask"]["price"]
        # FILA FIFO real: entra atras no nivel; so enche depois que o nivel for consumido
        if la.get("q_lvl") != pr:
            la["q_lvl"] = pr
            la["q_ahead"] = float(b.get("ba_sz") or 0)
        if now >= q["ask"]["active_at"] and price >= pr - 1e-9:
            sz = size
            if la.get("q_ahead", 0) > 0:
                tak = min(la["q_ahead"], sz)
                la["q_ahead"] -= tak
                sz -= tak
            if sz > 0:
                opp = next((x for x in m["tokens"] if x != tok), None)
                room = max(0.0, LA_NET_CAP - (la["inv"].get(opp, 0) if opp else 0))
                qty = min(sz, LA_ORD, la["inv"][tok] + room, max(0.0, LA_MAX_PER_TOKEN - la["sold"][tok]))
                need = max(0.0, qty - la["inv"][tok])
                if need > 0:
                    with LOCK:
                        gcash = sum(mm["la"]["cash"] for mm in STATE["markets"].values())
                    need = min(need, max(0.0, gcash + LA_BANCA), max(0.0, LA_USD - la["split"]))
                    qty = min(qty, la["inv"][tok] + need)
                qty = int(qty)
                if qty > 0:
                    if need > 0:
                        for t2 in m["tokens"]:
                            la["inv"][t2] += need
                        la["cash"] -= need
                        la["split"] += need
                    la["inv"][tok] -= qty
                    la["cash"] += qty * pr
                    la["sold"][tok] += qty
                    sig = ""
                    try:
                        info = clob_signer.sign(tok, "SELL", pr, qty)
                        if info.get("sig"):
                            sig = info.get("hash") or ("ASSINADA · sig " + info["sig"])
                    except Exception:
                        pass
                    la["fills"].append({"ts": int(now), "token": tok, "outcome": m["tokens"][tok],
                                        "price": pr, "size": qty, "signed": sig, "mid": mid, "adv": None})
                    db.la_fill(now, tok, m["tokens"][tok], pr, qty, mid, b.get("ba_sz") or 0)
                    mm2 = min(la["inv"].values())
                    if mm2 > 0:
                        for t2 in m["tokens"]:
                            la["inv"][t2] -= mm2
                        la["cash"] += mm2
                        la["merged"] = round(la["merged"] + mm2, 2)
    if side == "SELL" and now >= q["bid"]["active_at"] and price <= q["bid"]["price"] + 1e-9:
        qq = q["bid"]
        if qq.get("ahead", 0) > 0:                    # consome a fila na frente primeiro
            take = min(qq["ahead"], size); qq["ahead"] -= take; size -= take
        if size <= 0:
            return
        pr = qq["price"]
        room = max(0.0, (MAX_USD_PER_TOKEN / pr) - m["inv"][tok]) if pr > 0 else 0.0
        qty = min(QUOTE_SIZE, size, room) * HAIRCUT
        if qty > 0:
            m["inv"][tok] += qty
            m["cash"] -= qty * pr
            m["cost"] += qty * pr
            m["fills"].append({"ts": int(now), "token": tok, "outcome": m["tokens"][tok],
                               "asset": m["asset"], "side": "BUY", "price": pr, "size": qty,
                               "mid": mid, "edge": mid - pr})
            try:
                info = clob_signer.sign(tok, "BUY", pr, qty)
                m["fills"][-1]["signed"] = (info.get("hash") or
                                            ("ASSINADA · sig " + info["sig"]) if info.get("sig")
                                            else ("ERR " + info.get("err", "")))
            except Exception:
                pass
            with LOCK:
                STATE["totals"]["fills"] += 1
                STATE["totals"]["spread_captured"] += (mid - pr) * qty
                STATE["totals"]["shares_filled"] += qty
    elif side == "BUY" and now >= q["ask"]["active_at"] and price >= q["ask"]["price"] - 1e-9:
        qq = q["ask"]
        if qq.get("ahead", 0) > 0:
            take = min(qq["ahead"], size); qq["ahead"] -= take; size -= take
        if size <= 0:
            return
        pr = qq["price"]
        qty = min(QUOTE_SIZE, size, max(0.0, m["inv"][tok])) * HAIRCUT   # NAO shorta: so vende o que tem
        if qty > 0:
            m["inv"][tok] -= qty
            m["cash"] += qty * pr
            m["fills"].append({"ts": int(now), "token": tok, "outcome": m["tokens"][tok],
                               "asset": m["asset"], "side": "SELL", "price": pr, "size": qty,
                               "mid": mid, "edge": pr - mid})
            try:
                info = clob_signer.sign(tok, "SELL", pr, qty)
                m["fills"][-1]["signed"] = (info.get("hash") or
                                            ("ASSINADA · sig " + info["sig"]) if info.get("sig")
                                            else ("ERR " + info.get("err", "")))
            except Exception:
                pass
            with LOCK:
                STATE["totals"]["fills"] += 1
                STATE["totals"]["spread_captured"] += (pr - mid) * qty
                STATE["totals"]["shares_filled"] += qty


def settle_market(m):
    try:
        # Gamma resolve (o CLOB /markets/{id} costuma ficar closed=False nesses 5m)
        ev = net.get_json("https://gamma-api.polymarket.com/events?slug=%s" % m["slug"], tries=2)
        if not ev:
            return False
        mk = ev[0]["markets"][0]
        outs, prices = mk.get("outcomes"), mk.get("outcomePrices")
        if isinstance(outs, str):
            outs = json.loads(outs)
        if isinstance(prices, str):
            prices = json.loads(prices)
        prices = [float(p) for p in prices]
        mx = max(prices)
        # liquida quando o Gamma fecha OU quando um lado ja esta decidido (>=0.99)
        if not mk.get("closed") and mx < 0.99:
            return False
        win_out = outs[prices.index(mx)]
        db.resolution(m["cid"], win_out)
        win_tok = next((tk for tk, out in m["tokens"].items() if out == win_out), None)
        if win_tok is None:
            return False
        payout = m["inv"].get(win_tok, 0.0)      # shares do vencedor (neg se short)
        pnl = m["cash"] + payout                  # caixa + posicao marcada a mercado no fim
        m.update({"settled": True, "active": False, "winner": m["tokens"].get(win_tok),
                  "payout": payout, "pnl": pnl})
        # ---- LikeAnon settle: MERGE pares -> $1 cada; REDEEM vencedor ----
        la = m["la"]
        toks = list(m["tokens"])
        mx = min(la["inv"][t] for t in toks)
        if mx > 0:
            for t in toks:
                la["inv"][t] -= mx
            la["cash"] += mx
            la["merged"] = round(mx, 2)
        rede = max(0.0, la["inv"][win_tok])
        la["redeemed"] = round(rede, 2)
        la["pnl"] = round(la["cash"] + rede, 2)
        with LOCK:
            t = STATE["totals"]
            t["cost"] += m["cost"]; t["payout"] += payout; t["pnl"] += pnl; t["markets"] += 1
            t["wins" if pnl > 0 else "losses"] += 1
            STATE["settled"].append({
                "slug": m["slug"], "asset": m["asset"], "winner": m["winner"],
                "cost": round(m["cost"], 2), "payout": round(payout, 2), "pnl": round(pnl, 2),
                "cash": round(m["cash"], 2),
                "roi": round(100 * pnl / m["cost"], 2) if m["cost"] else 0.0,
                "inv": {m["tokens"][k]: round(v, 1) for k, v in m["inv"].items() if v},
                "fills": len(m["fills"]), "trades": m["trades"], "end": m["end"],
                "la_pnl": la["pnl"], "la_sold": round(sum(la["sold"].values()), 1),
                "la_split": round(la["split"], 1), "la_fills": len(la["fills"])})
            STATE["la_settled"].append({"slug": m["slug"], "pnl": la["pnl"],
                                        "sold": round(sum(la["sold"].values()), 1),
                                        "split": round(la["split"], 1)})
        return True
    except Exception as e:
        log_err("settle %s: %s" % (m["cid"][:8], e))
        return False


async def run_window():
    w = int(time.time() // DUR_SEC) * DUR_SEC
    end = w + DUR_SEC
    if time.time() > end - 5:            # perto do fim, espera a proxima
        await asyncio.sleep(end - time.time() + 1)
        return
    found = discover(w)
    markets = [register(*f) for f in found]
    tokens = [tok for m in markets for tok in m["tokens"]]
    if not tokens:
        await asyncio.sleep(3); return

    import websockets
    async with websockets.connect(
        WS_URL, open_timeout=15, ping_interval=20, ping_timeout=20,
        max_size=10 * 1024 * 1024, compression=None, close_timeout=5,
    ) as ws:
        await ws.send(json.dumps({"assets_ids": tokens, "type": "market"}))
        with LOCK:
            STATE["ws"] = "conectado (janela %d)" % w
        global TOK2M
        TOK2M = {tok: m for m in markets for tok in m["tokens"]}
        import websockets.exceptions as wexc
        missed = 0
        while time.time() < end + 2:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=5)
            except asyncio.TimeoutError:
                missed += 1
                if missed >= 3:
                    log_err("ws travado (sem msgs por ~15s); reconectando")
                    break
                continue
            except (wexc.ConnectionClosed, Exception) as e:
                log_err("ws caiu (%s)" % type(e).__name__)
                globals()["WS_RECONNECTS"] = globals().get("WS_RECONNECTS", 0) + 1
                break
            missed = 0
            globals()["WS_LAST_MSG"] = time.time()
            # leitura PURA: so empurra pra fila. Quem processa e' a thread processor.
            if MSGQ.qsize() > 5000:
                try:
                    MSGQ.get_nowait()
                    globals()["WS_DROPPED"] = globals().get("WS_DROPPED", 0) + 1
                except queue.Empty:
                    pass
            MSGQ.put_nowait(raw)
    with LOCK:
        STATE["ws"] = "reconectando..."
    for m in markets:
        if m["active"]:
            await asyncio.to_thread(settle_market, m)
    # limpa antigos
    with LOCK:
        for slug in list(STATE["markets"]):
            mm = STATE["markets"][slug]
            if not mm["active"] and time.time() > mm["end"] + 30:
                del STATE["markets"][slug]


def process_raw(raw):
    try:
        d = _loads(raw)
    except Exception:
        return
    for ev in (d if isinstance(d, list) else [d]):
        et = ev.get("event_type")
        m = TOK2M.get(ev.get("asset_id"))
        if m is None:
            continue
        if et == "book":
            on_book(m, ev)
        elif et == "price_change":
            on_price_change(m, ev)
        elif et == "last_trade_price":
            on_trade(m, ev)


def processor():
    """Processa as mensagens em thread separada p/ o socket nunca ficar lento."""
    while True:
        try:
            raw = MSGQ.get(timeout=2)
        except queue.Empty:
            continue
        try:
            process_raw(raw)
        except Exception:
            pass


def ws_main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    while True:
        try:
            loop.run_until_complete(run_window())
        except Exception:
            log_err("ws: " + traceback.format_exc().splitlines()[-1])
            time.sleep(2)


# ----------------------------- dashboard -----------------------------
def snapshot():
    with LOCK:
        markets = []
        for m in STATE["markets"].values():
            rows = []
            for tok, out in m["tokens"].items():
                bk = m["books"].get(tok, {}); q = m["quotes"].get(tok, {})
                qb = q.get("bid") or {}; qa = q.get("ask") or {}
                rows.append({"outcome": out, "bb": bk.get("bb"), "ba": bk.get("ba"),
                             "mid": bk.get("mid"),
                             "bid_q": qb.get("price"), "ask_q": qa.get("price"),
                             "qbid_active": qb.get("active_at", 0) <= time.time(),
                             "qask_active": qa.get("active_at", 0) <= time.time(),
                             "inv": round(m["inv"].get(tok, 0), 1)})
            markets.append({"slug": m["slug"], "asset": m["asset"], "end": m["end"],
                            "secs_left": max(0, m["end"] - int(time.time())), "cost": round(m["cost"], 2),
                            "fills": len(m["fills"]), "trades": m["trades"], "rows": rows})
        t = dict(STATE["totals"])
        t["avg_spread"] = (t["spread_captured"] / t["shares_filled"]) if t["shares_filled"] else 0.0
        # marcacao a mercado (PnL em aberto das janelas ainda nao liquidadas)
        open_pnl = _open_locked()
        open_cost = sum(m["cost"] for m in STATE["markets"].values())
        open_fills = sum(len(m["fills"]) for m in STATE["markets"].values())
        t["open_pnl"] = open_pnl
        t["open_cost"] = open_cost
        t["open_fills"] = open_fills
        t["peak_open"] = max(STATE["peak_open"], open_cost)
        t["banca"] = BANCA
        t["caixa_livre"] = BANCA - open_cost
        # NOSSAS entradas (fills abertos), detalhadas
        our_fills = []
        for m in STATE["markets"].values():
            for fl in m["fills"]:
                our_fills.append({"ts": fl["ts"], "market": m["asset"].upper(), "outcome": fl["outcome"],
                                  "side": fl["side"], "price": fl["price"], "size": fl["size"],
                                  "usd": round(fl["price"] * fl["size"], 2), "mid": fl.get("mid"),
                                  "edge": fl.get("edge"), "signed": fl.get("signed", "")})
        our_fills.sort(key=lambda x: x["ts"], reverse=True)
        our_fills = our_fills[:70]
        # --- comparacao com o alvo (on-chain, tempo real): "entramos junto?" ---
        tokeninfo, ourfills = {}, []
        for m in STATE["markets"].values():
            for tk, out in m["tokens"].items():
                tokeninfo[tk] = (m["asset"], out)
            ourfills.extend(m["fills"])
        tgt = []
        for x in STATE["target_fills"][:80]:
            d = dict(x)
            ai = tokeninfo.get(x["token"])
            d["asset"] = ai[0].upper() if ai else "?"
            d["outcome"] = ai[1] if ai else "?"
            d["matched"] = any(fl.get("token") == x["token"] and abs(fl["ts"] - x["t"]) <= MATCH_WINDOW_S
                               for fl in ourfills)
            tgt.append(d)
        matched = sum(1 for d in tgt if d["matched"])
        match = {"n": len(tgt), "matched": matched,
                 "pct": (100.0 * matched / len(tgt)) if tgt else 0.0, "window_s": MATCH_WINDOW_S}
        mstat = dict(STATE["mirror"])
        mstat["avg_slip"] = (mstat["slip_sum"] / mstat["n"]) if mstat["n"] else 0.0
        mstat["avg_late"] = (mstat["late_sum"] / mstat["n"]) if mstat["n"] else 0.0
        # --- Anon (real, data-api) ---
        anon_trades = list(STATE["anon"]["trades"][:60])
        anon_sell = round(sum((x["size"] or 0) * (x["price"] or 0) for x in anon_trades if x["side"] == "SELL"), 2)
        # "entrou junto": fills on-chain do Anon vs nossas vendas LikeAnon (mesmo token, ±window)
        la_tok = []
        for m in STATE["markets"].values():
            for f in m["la"]["fills"]:
                la_tok.append((f["token"], f["ts"]))
        af, amatch = [], 0
        for x in STATE["anon"]["fills"][:80]:
            d = dict(x)
            d["matched"] = any(tok == x["token"] and abs(ts - x["t"]) <= MATCH_WINDOW_S for tok, ts in la_tok)
            amatch += 1 if d["matched"] else 0
            af.append(d)
        anon = {"trades": anon_trades, "sell_usdc": anon_sell,
                "split": STATE["anon"]["split"], "merge": STATE["anon"]["merge"],
                "redeem": STATE["anon"]["redeem"], "pnl_total": STATE["anon"]["pnl_total"],
                "day_pnl": STATE["anon"]["day_pnl"], "curves": STATE["anon"]["curves"],
                "oc_fills": af, "oc": dict(STATE["anon"]["oc"]),
                "match": {"n": len(af), "matched": amatch,
                          "pct": (100.0 * amatch / len(af)) if af else 0.0, "window_s": MATCH_WINDOW_S}}
        # --- LikeAnon (nosso, a seco) ---
        la_inv = {}
        for m in STATE["markets"].values():
            for tk, o in m["tokens"].items():
                la_inv[o] = round(la_inv.get(o, 0) + m["la"]["inv"][tk], 1)
        la_entries = []
        for m in STATE["markets"].values():
            for f in m["la"]["fills"]:
                la_entries.append({"ts": f["ts"], "market": m["asset"].upper(), "outcome": f["outcome"],
                                   "price": f["price"], "size": f["size"],
                                   "usd": round(f["price"] * f["size"], 2),
                                   "signed": f.get("signed", "")})
        la_entries.sort(key=lambda x: x["ts"], reverse=True)
        la_entries = la_entries[:40]
        la_eq, c2 = [], 0.0
        for x in STATE["la_settled"]:
            c2 += x["pnl"]; la_eq.append(round(c2, 2))
        adv_total, adv_n = 0.0, 0
        for m in STATE["markets"].values():
            for f in m["la"]["fills"]:
                if f.get("adv") is not None:
                    adv_total += f["adv"] * f["size"]
                    adv_n += 1
        la_realized = round(sum(x["pnl"] for x in STATE["la_settled"]), 2)
        likeanon = {"realized": la_realized,
                    "banca": round(LA_BANCA + la_realized, 2),
                    "peak": round(STATE["la_peak"], 2),
                    "net": round(la_inv.get("Up", 0.0) - la_inv.get("Down", 0.0), 1),
                    "directional": abs(la_inv.get("Up", 0.0) - la_inv.get("Down", 0.0)) > 10,
                    "adverse": round(adv_total, 2), "adv_n": adv_n,
                    "pnl_adj": round(la_realized - max(0.0, adv_total), 2),
                    "open_cash": round(sum(m["la"]["cash"] for m in STATE["markets"].values()), 2),
                    "equity": la_eq,
                    "sold": round(sum(sum(m["la"]["sold"].values()) for m in STATE["markets"].values()), 1),
                    "split": round(sum(m["la"]["split"] for m in STATE["markets"].values()), 1),
                    "fills": sum(len(m["la"]["fills"]) for m in STATE["markets"].values()),
                    "inv": la_inv, "entries": la_entries,
                    "settled": list(reversed(STATE["la_settled"][-40:]))}
        eq, cum = [], 0.0
        for smk in STATE["settled"]:
            cum += smk["pnl"]; eq.append(round(cum, 2))
        return {"mode": STATE["mode"], "ws": STATE["ws"], "uptime": int(time.time() - STATE["started"]),
                "collect_s": int(time.time()) - db.collect_start(),
                "latency_ms": STATE["latency_ms"], "books_seen": STATE["books_seen"],
                "trades_seen": STATE["trades_seen"],
                "markets": sorted(markets, key=lambda x: x["slug"]),
                "settled": list(reversed(STATE["settled"][-60:])),
                "equity": eq, "pnl_series": list(STATE["pnl_series"]),
                "our_fills": our_fills,
                "recent_trades": STATE["recent_trades"],
                "target_trades": tgt, "match": match,
                "mirror": mstat, "onchain": dict(STATE["onchain"]),
                "anon": anon, "likeanon": likeanon,
                "arb": dict(STATE["arb"]),
                "signer": {"wallet": clob_signer.wallet(), "err": clob_signer._state["err"],
                           "post": os.environ.get("POLY_POST") == "1"},
                "totals": t, "errors": STATE["errors"], "target": TARGET_WALLET}


HTML = r"""<!doctype html><html lang="pt-br"><head><meta charset="utf-8">
<title>poli-mm — shadow market maker</title><style>
:root{--bg:#0b0e14;--card:#131722;--line:#222a3a;--tx:#e6edf3;--mut:#8b96a8;--grn:#2ea043;--red:#f85149;--blu:#4c8dff;--ylw:#d29922}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:13px/1.45 ui-monospace,Menlo,Consolas,monospace}
header{padding:14px 20px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px}
h1{font-size:15px;margin:0;font-weight:600}.badge{background:#1f2433;border:1px solid var(--line);border-radius:20px;padding:3px 10px;color:var(--ylw);font-size:12px}
.wrap{padding:16px 20px;max-width:1320px;margin:0 auto}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:18px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.card .k{color:var(--mut);font-size:11px;text-transform:uppercase}.card .v{font-size:20px;margin-top:4px;font-weight:600}
.g{color:var(--grn)}.r{color:var(--red)}.b{color:var(--blu)}
table{width:100%;border-collapse:collapse;margin:8px 0 22px}th,td{text-align:right;padding:7px 10px;border-bottom:1px solid var(--line);white-space:nowrap}
th:first-child,td:first-child{text-align:left}th{color:var(--mut);font-weight:500;font-size:11px;text-transform:uppercase}
tr:hover td{background:#161b28}h2{font-size:13px;color:var(--mut);text-transform:uppercase;margin:22px 0 6px}
.small{color:var(--mut);font-size:11px}.err{color:var(--red);font-size:11px}.q{color:var(--blu)}.off{color:var(--mut);opacity:.5}
.sell{color:var(--red)}.buy{color:var(--grn)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:18px}
.tabs{display:flex;gap:8px;padding:8px 20px;border-bottom:1px solid var(--line);background:#0d1118}
.tabs button{background:#161b28;color:var(--tx);border:1px solid var(--line);border-radius:8px;padding:7px 14px;cursor:pointer;font:13px ui-monospace,Menlo,Consolas,monospace}
.tabs button.on{background:#1f6feb33;border-color:#4c8dff;color:#8fb8ff}
.panel{border:1px solid var(--line);border-radius:10px;padding:12px;background:var(--card)}
.panels{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media(max-width:900px){.panels{grid-template-columns:1fr}}
canvas{width:100%;background:#0d1118;border:1px solid var(--line);border-radius:8px}
@media(max-width:900px){.grid2{grid-template-columns:1fr}}
</style></head><body>
<header><h1>poli-mm <span class="small">shadow MM · BTC/ETH/SOL 5m · WS</span></h1>
<div><span class="badge" id="mode">…</span> <span class="small" id="upd"></span></div></header>
<nav class="tabs"><button id="tab-mm" class="on" onclick="showTab('mm')">⚙ MM (atual)</button>
<button id="tab-anon" onclick="showTab('anon')">⚖ Anon vs LikeAnon</button>
<button id="tab-arb" onclick="showTab('arb')">🎯 ARB 100% neutro</button>
<a href="/" style="margin-left:auto;color:var(--mut);font-size:12px;align-self:center">refresh</a></nav>
<div class="wrap" id="mmview">
 <div class="grid" id="cards"></div>
 <div class="grid2">
  <div class="card"><div class="k">NOSSO bot — PnL acumulado / mercado liquidado</div><canvas id="ourchart" height="220"></canvas><div class="small" id="ourstat">aguardando mercados fecharem…</div></div>
  <div class="card"><div class="k">ALVO norm1e69 — PnL acumulado (histórico)</div><canvas id="tgtchart" height="220"></canvas><div class="small" id="tgtstat"></div></div>
 </div>
 <h2 style="color:#2ea043">NOSSO BOT — entradas / fills abertos</h2><div id="of"></div>
 <h2>Mercados ativos (WS tempo real)</h2><div id="mk"></div>
 <h2 style="color:#4c8dff">Trades do ALVO norm1e69 — &quot;entramos junto?&quot;</h2><div id="tt"></div>
 <h2>Trades recentes do mercado (side = agressor)</h2><div id="tr"></div>
 <h2>Liquidações (nossas)</h2><div id="st"></div>
 <h2>Diagnóstico</h2><div class="small" id="diag"></div>
</div>
<div class="wrap" id="anonview" style="display:none">
 <div class="grid2">
  <div class="panel">
   <h2 style="margin-top:0;color:#4c8dff">ANON (real · on-chain) <span class="small" id="anonh"></span></h2>
   <div style="margin:8px 0" id="anonperiods">
    <button onclick="drawAnon('1d')">1D</button>
    <button onclick="drawAnon('1w')">1W</button>
    <button onclick="drawAnon('1m')">1M</button>
    <button onclick="drawAnon('all')">ALL</button>
   </div>
   <canvas id="anonchart" height="200"></canvas>
   <div id="anonbody"></div>
   <h2 style="color:#4c8dff;margin:10px 0 4px">ANON — fills on-chain (tempo real)</h2><div id="anonoc"></div>
  </div>
  <div class="panel">
   <h2 style="margin-top:0;color:#2ea043">LIKEANON (nosso, a seco) · <span id="lashow"></span></h2>
   <canvas id="lachart" height="200"></canvas>
   <div id="labody"></div>
   <h2 style="color:#2ea043;margin:10px 0 4px">NOSSAS ENTRADAS ($)</h2><div id="laentries"></div>
  </div>
 </div>
</div>
<div class="wrap" id="arbview" style="display:none">
 <div class="grid" id="arbcards"></div>
 <h2 style="color:#d29922">ARB — operações travadas (par comprado/vendido junto) · <span class="small">0% direcional por construção</span></h2>
 <div id="arbbody"></div>
</div><script>
function f(x,d){return x==null?'—':Number(x).toFixed(d==null?2:d)}
function money(x){return `<span class="${x>=0?'g':'r'}">${x>=0?'+':''}$${f(x)}</span>`}
function fmtDur(s){s=Math.max(0,s|0);const d=(s/86400)|0,h=((s%86400)/3600)|0,m=((s%3600)/60)|0,ss=s%60;
 return (d?d+'d ':'')+(h?h+'h ':'')+(m?m+'m ':'')+ss+'s';}
let TARGET=null;
fetch('/target').then(r=>r.json()).then(t=>{TARGET=t;drawTgt();}).catch(()=>{});
function drawChart(cv,data,color){
 const W=cv.width=cv.clientWidth*2||1000,H=cv.height=440,ctx=cv.getContext('2d'),pad=54;
 ctx.clearRect(0,0,W,H);ctx.fillStyle='#0d1118';ctx.fillRect(0,0,W,H);
 if(!data||data.length<2){ctx.fillStyle='#8b96a8';ctx.font='26px monospace';ctx.fillText('sem dados ainda',pad,pad+30);return}
 const mn=Math.min(0,...data),mx=Math.max(0,...data);
 const x=i=>pad+(W-2*pad)*(data.length<2?0:i/(data.length-1));
 const y=v=>H-pad-(H-2*pad)*((v-mn)/((mx-mn)||1));
 ctx.strokeStyle='#222a3a';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(pad,y(0));ctx.lineTo(W-pad,y(0));ctx.stroke();
 ctx.strokeStyle=color;ctx.lineWidth=3;ctx.beginPath();
 data.forEach((v,i)=>{i?ctx.lineTo(x(i),y(v)):ctx.moveTo(x(i),y(v))});ctx.stroke();
 ctx.fillStyle='#8b96a8';ctx.font='22px monospace';
 ctx.fillText('$'+mx.toFixed(0),6,pad);ctx.fillText('$'+mn.toFixed(0),6,H-pad);
}
function drawTgt(){if(!TARGET)return;drawChart(document.getElementById('tgtchart'),TARGET.equity,'#4c8dff');
 document.getElementById('tgtstat').textContent=(TARGET.title||'')+' · '+(TARGET.roi||0)+'%/merc · win '+(TARGET.winrate||0)+'%';}
window._anonPeriod='1d';
function drawAnon(iv){window._anonPeriod=iv;const an=(window._lastState||{}).anon;if(!an||!an.curves||!an.curves[iv])return;drawChart(document.getElementById('anonchart'),an.curves[iv].map(p=>p[1]),'#4c8dff');}
function showTab(t){document.getElementById('mmview').style.display=(t==='mm')?'':'none';
 document.getElementById('anonview').style.display=(t==='anon')?'':'none';
 document.getElementById('arbview').style.display=(t==='arb')?'':'none';
 document.getElementById('tab-mm').className=(t==='mm')?'on':'';
 document.getElementById('tab-anon').className=(t==='anon')?'on':'';
 document.getElementById('tab-arb').className=(t==='arb')?'on':'';}
async function tick(){let s;try{s=await(await fetch('/state')).json()}catch(e){return}
 window._lastState=s;
 document.getElementById('mode').textContent=s.mode+' · '+s.ws;
 document.getElementById('upd').textContent='lat '+s.latency_ms+'ms · up '+s.uptime+'s · books '+s.books_seen+' · trades '+s.trades_seen+' · onchain bloco '+s.onchain.last_block+' ('+s.onchain.events+' fills alvo) · assinador '+((s.signer&&s.signer.wallet)?(s.signer.wallet.slice(0,8)+'..'+(s.signer.post?' POST ON':' assina-sem-enviar')):'OFF');
 const t=s.totals,wr=t.markets?100*t.wins/t.markets:0;
 document.getElementById('cards').innerHTML=`
 <div class="card"><div class="k">Tempo de coleta</div><div class="v b">${fmtDur(s.collect_s)}</div><div class="small">desde o último reset</div></div>
 <div class="card"><div class="k">PnL realizado</div><div class="v">${money(t.pnl)}</div><div class="small">${t.markets} merc. fechados</div></div>
 <div class="card"><div class="k">PnL em aberto</div><div class="v">${money(t.open_pnl)}</div><div class="small">janela atual</div></div>
 <div class="card"><div class="k">Investido (aberto)</div><div class="v">$${f(t.open_cost)}</div><div class="small">de $${f(t.banca)} (${f(100*t.open_cost/(t.banca||1),0)}%)</div></div>
 <div class="card"><div class="k">Pico em aberto</div><div class="v">$${f(t.peak_open)}</div><div class="small">banca mín. ~$${f(t.peak_open*2.5)} (2,5×)</div></div>
 <div class="card"><div class="k">Caixa livre</div><div class="v">$${f(t.caixa_livre)}</div></div>
 <div class="card"><div class="k">Fills</div><div class="v">${t.fills + t.open_fills} <span class="small">(${t.open_fills} abertos)</span></div></div>
 <div class="card"><div class="k">Spread médio</div><div class="v b">${f(100*t.avg_spread,2)}¢</div></div>
 <div class="card"><div class="k">Entrou junto (alvo)</div><div class="v ${s.match.pct>30?'g':'r'}">${f(s.match.pct,0)}%</div><div class="small">${s.match.matched}/${s.match.n} em ±${s.match.window_s}s</div></div>
 <div class="card"><div class="k">Slippage cópia</div><div class="v ${s.mirror.avg_slip>=0?'r':'g'}">${f(100*s.mirror.avg_slip,2)}¢</div><div class="small">${s.mirror.n} fills do alvo</div></div>
 <div class="card"><div class="k">Lag detecção</div><div class="v">${f(s.mirror.avg_late,1)}s</div><div class="small">on-chain</div></div>
 <div class="card"><div class="k">Alvo ${s.target.name}</div><div class="v">${f(100*s.target.edge,2)}% <span class="small">/merc</span></div></div>`;
 drawChart(document.getElementById('ourchart'),(s.pnl_series||[]).map(p=>p[1]),'#2ea043');
 document.getElementById('ourstat').textContent='PnL total $'+f(t.pnl+t.open_pnl)+' (realizado $'+f(t.pnl)+' + aberto $'+f(t.open_pnl)+') · '+t.markets+' merc. fechados';
 let ho='<table><tr><th>hora</th><th>mkt</th><th>lado</th><th>side</th><th>preço</th><th>size</th><th>$</th><th>mid</th><th>edge</th><th>ordem assinada (real/sem envio)</th></tr>';
 for(const r of s.our_fills){ho+=`<tr><td>${new Date(r.ts*1000).toLocaleTimeString()}</td><td>${r.market}</td><td>${r.outcome}</td>
  <td class="${r.side==='SELL'?'sell':'buy'}">${r.side}</td><td>${f(r.price,2)}</td><td>${f(r.size,1)}</td><td>$${f(r.usd)}</td><td>${f(r.mid,3)}</td>
  <td class="${(r.edge||0)>=0?'g':'r'}">${f(100*(r.edge||0),2)}¢</td>
  <td class="small">${r.signed?r.signed:'—'}</td></tr>`}
 document.getElementById('of').innerHTML=(s.our_fills.length?ho+'</table>':'<div class="small">nenhuma entrada nossa ainda…</div>');
 let h='<table><tr><th>Mercado</th><th>fecha</th><th>lado</th><th>bid</th><th>ask</th><th>mid</th><th>nosso bid</th><th>nosso ask</th><th>inv</th></tr>';
 for(const m of s.markets){for(let i=0;i<m.rows.length;i++){const r=m.rows[i];
  h+=`<tr><td>${i===0?m.asset.toUpperCase()+' '+m.secs_left+'s':''}</td><td>${i===0?'trades '+m.trades:''}</td>
  <td>${r.outcome}</td><td>${f(r.bb)}</td><td>${f(r.ba)}</td><td>${f(r.mid,3)}</td>
  <td class="q">${r.bid_q==null?'—':f(r.bid_q)+(r.qbid_active?'':'*')}</td>
  <td class="q">${r.ask_q==null?'—':f(r.ask_q)+(r.qask_active?'':'*')}</td>
  <td>${f(r.inv,1)}</td></tr>`}}
 document.getElementById('mk').innerHTML=h+'</table>';
 h='<table><tr><th>hora</th><th>ativo</th><th>lado</th><th>side</th><th>preço</th><th>size</th></tr>';
 for(const r of s.recent_trades){h+=`<tr><td>${new Date(r.t*1000).toLocaleTimeString()}</td><td>${r.asset.toUpperCase()}</td><td>${r.outcome}</td>
  <td class="${r.side==='SELL'?'sell':'buy'}">${r.side}</td><td>${f(r.price,2)}</td><td>${f(r.size,1)}</td></tr>`}
 document.getElementById('tr').innerHTML=h+'</table>';
 h='<table><tr><th>hora</th><th>ativo</th><th>lado</th><th>side</th><th>preço</th><th>size</th><th>nós entramos junto?</th></tr>';
 for(const r of s.target_trades){h+=`<tr><td>${new Date(r.t*1000).toLocaleTimeString()}</td><td>${r.asset}</td><td>${r.outcome}</td>
  <td class="${r.side==='SELL'?'sell':'buy'}">${r.side}</td><td>${f(r.price,2)}</td><td>${f(r.size,1)}</td>
  <td class="${r.matched?'g':'small'}">${r.matched?'✔ SIM':'— não'}</td></tr>`}
 document.getElementById('tt').innerHTML=(s.target_trades.length?h+'</table>':'<div class="small">sem fills do alvo ainda (on-chain ao vivo). aguarde…</div>');
 h='<table><tr><th>mercado</th><th>venceu</th><th>investido</th><th>payout</th><th>PnL</th><th>ROI</th><th>fills</th><th>inv final</th></tr>';
 for(const m of s.settled){h+=`<tr><td>${m.slug}</td><td>${m.winner}</td><td>$${f(m.cost)}</td><td>$${f(m.payout)}</td>
  <td>${money(m.pnl)}</td><td class="${(m.roi||0)>=0?'g':'r'}">${f(m.roi,2)}%</td><td>${m.fills}</td><td class="small">${JSON.stringify(m.inv)}</td></tr>`}
 document.getElementById('st').innerHTML=h+'</table>';
 document.getElementById('diag').innerHTML=(s.errors.slice(-6).map(x=>`<div class="err">${x}</div>`).join('')||'sem erros')+
 (s.onchain.err?`<div class="err">onchain: ${s.onchain.err}</div>`:'')+
 '<div class="small">* quote ainda em latência. Fill nosso = trade SELL no nível do nosso bid. Alvo = OrderFilled on-chain. DRY: nenhuma ordem real enviada.</div>';
 // ==== Anon vs LikeAnon ====
 const an=s.anon||{trades:[],sell_usdc:0,split:0,merge:0,redeem:0,net:0};
 const la=s.likeanon||{realized:0,open_cash:0,sold:0,split:0,fills:0,inv:{},settled:[]};
 document.getElementById('anonh').textContent='PnL total $'+f(an.pnl_total)+' · entrou junto '+f((an.match||{}).pct||0,0)+'% ('+((an.match||{}).matched||0)+'/'+((an.match||{}).n||0)+')';
 let ah='<div class="grid" style="margin-bottom:10px">'
  +`<div class="card"><div class="k">Vendas (janela)</div><div class="v">$${f(an.sell_usdc)}</div></div>`
  +`<div class="card"><div class="k">SPLIT</div><div class="v">$${f(an.split)}</div></div>`
  +`<div class="card"><div class="k">MERGE</div><div class="v">$${f(an.merge)}</div></div>`
  +`<div class="card"><div class="k">REDEEM</div><div class="v">$${f(an.redeem)}</div></div>`
  +`<div class="card"><div class="k">PnL total</div><div class="v ${an.pnl_total>=0?'g':'r'}">$${f(an.pnl_total)}</div></div>`
  +`<div class="card"><div class="k">PnL hoje</div><div class="v ${an.day_pnl>=0?'g':'r'}">$${f(an.day_pnl)}</div><div class="small">v2/user-pnl</div></div></div>`;
 ah+='<table><tr><th>hora</th><th>mercado</th><th>side</th><th>preço</th><th>size</th></tr>';
 for(const r of an.trades.slice(0,25)){ah+=`<tr><td>${new Date(r.t*1000).toLocaleTimeString()}</td><td>${r.title}</td><td class="${r.side==='SELL'?'sell':'buy'}">${r.side}</td><td>${f(r.price,2)}</td><td>${f(r.size,1)}</td></tr>`}
 document.getElementById('anonbody').innerHTML=ah+'</table>';
 let ao='<table><tr><th>hora</th><th>token</th><th>side</th><th>preço</th><th>size</th><th>nós junto?</th></tr>';
 for(const r of (an.oc_fills||[]).slice(0,25)){ao+=`<tr><td>${new Date(r.t*1000).toLocaleTimeString()}</td><td class="small">${String(r.token).slice(0,8)}…</td><td class="${r.side==='SELL'?'sell':'buy'}">${r.side}</td><td>${f(r.price,2)}</td><td>${f(r.size,1)}</td><td class="${r.matched?'g':'small'}">${r.matched?'✔ SIM':'— não'}</td></tr>`}
 document.getElementById('anonoc').innerHTML=(an.oc_fills&&an.oc_fills.length)?ao+'</table>':'<div class="small">sem fills on-chain do Anon ainda…</div>';
 let lh='<div class="grid" style="margin-bottom:10px">'
  +`<div class="card"><div class="k">Tempo de coleta</div><div class="v b">${fmtDur(s.collect_s)}</div><div class="small">último reset</div></div>`
  +`<div class="card"><div class="k">Direcional? (auditoria)</div><div class="v ${la.directional?'r':'g'}">${la.directional?'SIM':'NÃO ✓'}</div><div class="small">${la.directional?'FALHOU a neutralidade':'neutro, cumprindo a regra'}</div></div>`
  +`<div class="card"><div class="k">Exposição líquida (Up−Down)</div><div class="v ${Math.abs(la.net)>10?'r':'g'}">${f(la.net,1)}</div><div class="small">tem que ficar ~0</div></div>`
  +`<div class="card"><div class="k">Entrou junto (Anon)</div><div class="v ${an.match.pct>30?'g':'r'}">${f(an.match.pct,0)}%</div><div class="small">${an.match.matched}/${an.match.n}</div></div>`
  +`<div class="card"><div class="k">PnL realizado</div><div class="v ${la.realized>=0?'g':'r'}">$${f(la.realized)}</div><div class="small">${la.settled.length} merc</div></div>`
  +`<div class="card"><div class="k">Caixa aberto</div><div class="v">$${f(la.open_cash)}</div></div>`
  +`<div class="card"><div class="k">Vendido</div><div class="v">${f(la.sold,0)} sh</div></div>`
  +`<div class="card"><div class="k">SPLIT</div><div class="v">${f(la.split,0)} sh</div></div>`
  +`<div class="card"><div class="k">Fills</div><div class="v">${la.fills}</div></div>`
  +`<div class="card"><div class="k">Pico aberto</div><div class="v">$${f(la.peak)}</div><div class="small">máx. de $100</div></div>`
  +`<div class="card"><div class="k">Seleção adversa</div><div class="v ${la.adverse>0?'r':'g'}">$${f(la.adverse)}</div><div class="small">${la.adv_n} amostras</div></div>`
  +`<div class="card"><div class="k">PnL AJUSTADO</div><div class="v ${la.pnl_adj>=0?'g':'r'}">$${f(la.pnl_adj)}</div><div class="small">conservador</div></div>`
  +`<div class="card"><div class="k">Inventário (Up · Down)</div><div class="v" style="font-size:14px">${f(la.inv.Up||0,1)} · ${f(la.inv.Down||0,1)}</div></div></div>`;
 lh+='<table><tr><th>mercado</th><th>PnL</th><th>vendido</th><th>split</th></tr>';
 for(const r of la.settled){lh+=`<tr><td>${r.slug}</td><td class="${r.pnl>=0?'g':'r'}">$${f(r.pnl)}</td><td>${f(r.sold,0)}</td><td>${f(r.split,0)}</td></tr>`}
 document.getElementById('labody').innerHTML=lh+'</table>';
 let ent='<table><tr><th>hora</th><th>mkt</th><th>lado</th><th>preço</th><th>sh</th><th>$</th><th>assinada</th></tr>';
 for(const e of (la.entries||[])){ent+=`<tr><td>${new Date(e.ts*1000).toLocaleTimeString()}</td><td>${e.market}</td><td>${e.outcome}</td><td>${f(e.price,2)}</td><td>${f(e.size,1)}</td><td>$${f(e.usd)}</td><td class="small">${e.signed||'—'}</td></tr>`}
 document.getElementById('laentries').innerHTML=(la.entries&&la.entries.length)?ent+'</table>':'<div class="small">sem entradas ainda…</div>';
 document.getElementById('lashow').textContent='banca ATUAL $'+f(la.banca)+' (início $100) · caixa aberto $'+f(la.open_cash)+' · '+(la.fills||0)+' entradas';
 drawChart(document.getElementById('lachart'),(la.equity||[]),'#2ea043');
 drawAnon(window._anonPeriod);
 // ==== ARB 100% neutro ====
 const ar=s.arb||{pnl:0,sets:0,buy:0,sell:0,events:[]};
 document.getElementById('arbcards').innerHTML=
  `<div class="card"><div class="k">PnL travado (arb)</div><div class="v ${ar.pnl>=0?'g':'r'}">$${f(ar.pnl)}</div></div>`
  +`<div class="card"><div class="k">Pares executados</div><div class="v">${ar.sets}</div></div>`
  +`<div class="card"><div class="k">Comprou par (Σask&lt;1)</div><div class="v">${ar.buy}</div></div>`
  +`<div class="card"><div class="k">Vendeu par (Σbid&gt;1)</div><div class="v">${ar.sell}</div></div>`
  +`<div class="card"><div class="k">Direcional</div><div class="v g">0% ✓</div><div class="small">sempre as 2 pernas juntas</div></div>`;
 let ab='<table><tr><th>hora</th><th>ativo</th><th>tipo</th><th>Σ preço</th><th>lucro/par</th></tr>';
 for(const e of (ar.events||[])){ab+=`<tr><td>${new Date(e.ts*1000).toLocaleTimeString()}</td><td>${e.asset}</td><td>${e.side}</td><td>${f(e.combo,3)}</td><td class="g">$${f(e.profit,4)}</td></tr>`}
 document.getElementById('arbbody').innerHTML=(ar.events&&ar.events.length)?ab+'</table>':'<div class="small">sem oportunidade ainda — Σask&lt;1 ou Σbid&gt;1 é raro. aguardando…</div>';}
tick();setInterval(tick,1200);
</script></body></html>"""


AUTH_USER = "dudu"
AUTH_PASS = "123"

LOGIN_HTML = r"""<!doctype html><html lang="pt-br"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>poli-mm — login</title>
<style>body{margin:0;height:100vh;display:flex;align-items:center;justify-content:center;
background:#0b0e14;color:#e6edf3;font:14px ui-monospace,Menlo,Consolas,monospace}
.box{background:#131722;border:1px solid #222a3a;border-radius:12px;padding:26px 28px;width:300px}
h1{font-size:15px;margin:0 0 16px}label{display:block;color:#8b96a8;font-size:11px;margin:10px 0 4px}
input[type=text],input[type=password]{width:100%;box-sizing:border-box;background:#0d1118;border:1px solid #222a3a;color:#e6edf3;border-radius:8px;padding:9px}
.row{display:flex;align-items:center;gap:8px;margin:12px 0}
button{width:100%;background:#1f6feb;border:0;color:#fff;border-radius:8px;padding:10px;cursor:pointer;font:14px inherit}
.err{color:#f85149;font-size:12px;margin-top:8px}</style></head><body>
<form class="box" method="post" action="/login">
<h1>poli-mm</h1>
<label>usuário</label><input type="text" name="user" autofocus>
<label>senha</label><input type="password" name="pass">
<div class="row"><input type="checkbox" name="remember" id="rm"><label for="rm" style="margin:0">lembrar senha</label></div>
<button type="submit">entrar</button>
__ERR__
</form></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _authed(self):
        return "pm_auth=ok" in (self.headers.get("Cookie") or "")

    def _send(self, body, ctype, cookie=None, code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, loc, cookie=None):
        self.send_response(302)
        self.send_header("Location", loc)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()

    def do_GET(self):
        if self.path.startswith("/login"):
            err = '<div class="err">usuário ou senha inválidos</div>' if "e=1" in self.path else ""
            self._send(LOGIN_HTML.replace("__ERR__", err).encode(), "text/html; charset=utf-8")
            return
        if self.path.startswith("/logout"):
            self._redirect("/login", "pm_auth=; Path=/; Max-Age=0")
            return
        if self.path.startswith("/healthz"):
            body = json.dumps({
                "ok": True,
                "ts": int(time.time()),
                "ws": STATE.get("ws"),
                "last_msg_age_s": round(time.time() - WS_LAST_MSG, 1) if WS_LAST_MSG else None,
                "ws_reconnects": WS_RECONNECTS,
                "ws_dropped": WS_DROPPED,
                "queue": MSGQ.qsize(),
                "trades_seen": STATE.get("trades_seen"),
                "json_fast": JSON_FAST,
            }).encode()
            self._send(body, "application/json")
            return
        if not self._authed():
            self._redirect("/login")
            return
        if self.path.startswith("/reset"):
            with LOCK:
                db.reset()
                STATE["markets"] = {}
                globals()["TOK2M"] = {}
                STATE["settled"] = []
                STATE["la_settled"] = []
                STATE["target_fills"] = []
                STATE["target_trades"] = []
                STATE["recent_trades"] = []
                STATE["pnl_series"] = []
                STATE["peak_open"] = 0.0
                STATE["la_peak"] = 0.0
                STATE["books_seen"] = 0
                STATE["trades_seen"] = 0
                STATE["totals"] = {"cost": 0.0, "payout": 0.0, "pnl": 0.0, "fills": 0,
                                   "markets": 0, "wins": 0, "losses": 0,
                                   "spread_captured": 0.0, "shares_filled": 0.0}
                STATE["mirror"] = {"n": 0, "slip_sum": 0.0, "late_sum": 0.0}
                STATE["onchain"] = {"last_block": STATE["onchain"].get("last_block", 0),
                                     "events": 0, "err": ""}
                STATE["anon"]["oc"] = {"last_block": STATE["anon"].get("oc", {}).get("last_block", 0),
                                        "events": 0, "err": ""}
                STATE["anon"]["trades"] = []
                STATE["anon"]["trades"] = []
                STATE["anon"]["fills"] = []
                STATE["anon"]["sell_usdc"] = 0.0
                STATE["anon"]["split"] = 0.0
                STATE["anon"]["merge"] = 0.0
                STATE["anon"]["redeem"] = 0.0
                STATE["anon"]["curves"] = {}
                STATE["errors"] = ["%s reset executado" % time.strftime("%H:%M:%S")]
                STATE["last_reset"] = int(time.time())
            self._redirect("/")
            return
        if self.path.startswith("/state"):
            body = json.dumps(snapshot()).encode(); ctype = "application/json"
        elif self.path.startswith("/target"):
            body = json.dumps(TARGET_HIST).encode(); ctype = "application/json"
        else:
            body = HTML.encode(); ctype = "text/html; charset=utf-8"
        self._send(body, ctype)

    def do_POST(self):
        if self.path.startswith("/login"):
            import urllib.parse
            n = int(self.headers.get("Content-Length", "0") or 0)
            d = urllib.parse.parse_qs(self.rfile.read(n).decode())
            u = (d.get("user") or [""])[0]
            p = (d.get("pass") or [""])[0]
            rem = d.get("remember")
            if u == AUTH_USER and p == AUTH_PASS:
                ck = "pm_auth=ok; Path=/; HttpOnly; SameSite=Lax"
                if rem:
                    ck += "; Max-Age=2592000"
                self._redirect("/", ck)
            else:
                self._redirect("/login?e=1")
            return
        self._redirect("/login")


def _rpc(method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(POLY_RPC, data=body,
                                 headers={"content-type": "application/json", "user-agent": "curl/8.0"})
    return json.loads(urllib.request.urlopen(req, timeout=25).read())


def _words(datahex):
    d = datahex[2:]
    return [d[i:i + 64] for i in range(0, len(d), 64)]


def _decode_fill(lg, me=None):
    """Decodifica um OrderFilled de 4 topics envolvendo a carteira alvo."""
    try:
        topics = lg["topics"]
        if len(topics) < 4:
            return None
        maker = "0x" + topics[2][-40:].lower()
        taker = "0x" + topics[3][-40:].lower()
        w = _words(lg["data"])
        maker_asset, taker_asset = int(w[0], 16), int(w[1], 16)
        maker_amt, taker_amt = int(w[2], 16), int(w[3], 16)
        me = (me or TARGET_WALLET["address"]).lower()
        COLL = (0, 1)
        if maker_asset in COLL and taker_asset not in COLL:
            token = str(taker_asset)
            side = "BUY" if maker == me else ("SELL" if taker == me else None)
        elif taker_asset in COLL and maker_asset not in COLL:
            token = str(maker_asset)
            side = "SELL" if maker == me else ("BUY" if taker == me else None)
        else:
            return None
        shares = max(maker_amt, taker_amt) / 1e6
        usdc = min(maker_amt, taker_amt) / 1e6
        if me == ANON_ADDR.lower():
            side = "SELL"          # Anon opera como vendedor (data-api); corrige inversao maker/taker
        if side is None or shares <= 0:
            return None
        return {"t": int(lg.get("blockTimestamp", "0x0"), 16), "token": token,
                "price": round(usdc / shares, 4), "size": round(shares, 2), "side": side,
                "tx": lg["transactionHash"], "block": int(lg["blockNumber"], 16)}
    except Exception:
        return None


def mirror(new_fills):
    """Simula entrar JUNTO: se ele compra, olhamos o ASK vigente do nosso livro agora."""
    with LOCK:
        tok2book = {}
        for m in STATE["markets"].values():
            for tk in m["tokens"]:
                b = m["books"].get(tk)
                if b:
                    tok2book[tk] = b
        mf = STATE["mirror"]
        for f in new_fills:
            if f["side"] != "BUY":
                continue
            b = tok2book.get(f["token"])
            if not b or b.get("ba") is None:
                continue
            mf["n"] += 1
            mf["slip_sum"] += (b["ba"] - f["price"])
            mf["late_sum"] += (time.time() - f["t"])


def onchain_poller():
    """Le os OrderFilled da carteira alvo direto do Polygon (~2s/bloco)."""
    last = None
    while True:
        try:
            bn = int(_rpc("eth_blockNumber", [])["result"], 16)
            if last is None:
                last = bn - 45
            frm = max(last + 1, bn - 90)
            logs = []
            for pos in (2, 3):
                r = _rpc("eth_getLogs", [{"fromBlock": hex(frm), "toBlock": hex(bn),
                                          "address": EXCHANGE, "topics": [[]] * pos + [TARGET_TOPIC]}])
                logs += r.get("result", [])
            new = [f for f in (_decode_fill(lg) for lg in logs) if f]
            with LOCK:
                STATE["onchain"]["last_block"] = bn
                STATE["onchain"]["err"] = ""
                if new:
                    STATE["target_fills"].extend(new)
                    STATE["target_fills"].sort(key=lambda x: (x["t"], x["block"]), reverse=True)
                    STATE["target_fills"] = STATE["target_fills"][:300]
                    STATE["onchain"]["events"] += len(new)
            if new:
                mirror(new)
            last = bn
        except Exception as e:
            with LOCK:
                STATE["onchain"]["err"] = str(e)[:90]
        time.sleep(2)


def anon_onchain_poller():
    """Fills do ANON on-chain em tempo real (~2s/bloco)."""
    last = None
    while True:
        try:
            bn = int(_rpc("eth_blockNumber", [])["result"], 16)
            if last is None:
                last = bn - 45
            frm = max(last + 1, bn - 90)
            logs = []
            for pos in (2, 3):
                r = _rpc("eth_getLogs", [{"fromBlock": hex(frm), "toBlock": hex(bn),
                                          "address": EXCHANGE, "topics": [[]] * pos + [ANON_TOPIC]}])
                logs += r.get("result", [])
            new = [f for f in (_decode_fill(lg, ANON_ADDR) for lg in logs) if f]
            with LOCK:
                STATE["anon"]["oc"]["last_block"] = bn
                STATE["anon"]["oc"]["err"] = ""
                if new:
                    STATE["anon"]["fills"].extend(new)
                    STATE["anon"]["fills"].sort(key=lambda x: (x["t"], x["block"]), reverse=True)
                    STATE["anon"]["fills"] = STATE["anon"]["fills"][:400]
                    STATE["anon"]["oc"]["events"] += len(new)
            for f in new:
                db.anon_fill(f["t"], f["token"], f["side"], f["price"], f["size"])
            last = bn
        except Exception as e:
            with LOCK:
                STATE["anon"]["oc"]["err"] = str(e)[:90]
        time.sleep(2)


def anon_poller():
    """Le os trades/atividade REAIS do Anon (data-api) p/ o painel esquerdo."""
    seen = set()
    while True:
        try:
            tr = net.get_json("https://data-api.polymarket.com/trades?user=%s&limit=100&takerOnly=false" % ANON_ADDR, tries=2)
        except Exception:
            tr = None
        if tr:
            with LOCK:
                for t in tr:
                    key = (t.get("transactionHash"), t.get("asset"), t.get("timestamp"))
                    if key in seen:
                        continue
                    seen.add(key)
                    STATE["anon"]["trades"].append({
                        "t": int(t["timestamp"]), "title": (t.get("title") or "")[:28],
                        "side": t.get("side"), "price": t.get("price"), "size": t.get("size")})
                STATE["anon"]["trades"] = sorted(STATE["anon"]["trades"], key=lambda x: x["t"], reverse=True)[:80]
        with LOCK:
            STATE["anon"]["err"] = "api_n=%d t=%d" % (len(tr) if tr else 0, len(STATE["anon"]["trades"]))
        try:
            act = net.get_json("https://data-api.polymarket.com/activity?user=%s&limit=100" % ANON_ADDR, tries=1)
        except Exception:
            act = None
        if act:
            with LOCK:
                STATE["anon"]["split"] = round(sum((a.get("usdcSize") or 0) for a in act if a.get("type") == "SPLIT"), 2)
                STATE["anon"]["merge"] = round(sum((a.get("usdcSize") or 0) for a in act if a.get("type") == "MERGE"), 2)
                STATE["anon"]["redeem"] = round(sum((a.get("usdcSize") or 0) for a in act if a.get("type") == "REDEEM"), 2)
        try:
            for iv in ("1d", "1w", "1m", "all"):
                d = net.get_json("https://data-api.polymarket.com/v2/user-pnl?user=%s&interval=%s&fidelity=1h" % (ANON_ADDR, iv), tries=1)
                ptss = (d or {}).get("data", {}).get("points") or []
                if ptss:
                    ser = [[int(p.get("timestamp") or 0), round(float(p.get("economic_pnl") or 0), 2)] for p in ptss]
                    with LOCK:
                        STATE["anon"]["curves"][iv] = ser[::max(1, len(ser) // 250)]
                        STATE["anon"]["pnl_total"] = ser[-1][1]
                        if len(ser) >= 2:
                            STATE["anon"]["day_pnl"] = round(ser[-1][1] - ser[-2][1], 2)
        except Exception:
            pass
        time.sleep(4)


def settler():
    """Liquida mercados vencidos independentemente do WS (nunca deixa passar)."""
    while True:
        now = time.time()
        with LOCK:
            todo = [m for m in STATE["markets"].values() if m["active"] and now > m["end"] + 3]
        for m in todo:
            settle_market(m)
        with LOCK:
            for slug in list(STATE["markets"]):
                mm = STATE["markets"][slug]
                if not mm["active"] and time.time() > mm["end"] + 30:
                    del STATE["markets"][slug]
        time.sleep(3)


def main():
    net.install(verbose=True)
    dbpath = os.environ.get("PM_DB") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "pm.db")
    db.init(dbpath)
    print("[poli-mm] DB:", dbpath)
    threading.Thread(target=processor, daemon=True).start()
    threading.Thread(target=ws_main, daemon=True).start()
    threading.Thread(target=onchain_poller, daemon=True).start()
    threading.Thread(target=anon_onchain_poller, daemon=True).start()
    threading.Thread(target=anon_poller, daemon=True).start()
    threading.Thread(target=settler, daemon=True).start()
    threading.Thread(target=sampler, daemon=True).start()
    port = int(os.environ.get("PORT", HTTP_PORT))
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print("[poli-mm] dashboard em 0.0.0.0:%d  (DRY, WS)" % port)
    srv.serve_forever()


if __name__ == "__main__":
    main()
