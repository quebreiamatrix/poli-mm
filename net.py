"""Bypass de DNS via Cloudflare (DoH em 1.1.1.1).

O DNS local desta maquina bloqueia os dominios da Polymarket. Aqui resolvemos
cada host via DNS-over-HTTPS na Cloudflare e forcamos socket.getaddrinfo a
usar esses IPs — o TLS/SNI continua com o hostname correto, exatamente como
o `curl --resolve`.
"""
import json
import socket
import ssl
import urllib.request

HOSTS = [
    "gamma-api.polymarket.com",
    "clob.polymarket.com",
    "data-api.polymarket.com",
    "lb-api.polymarket.com",
    "user-pnl-api.polymarket.com",
    "polymarket.com",
    "ws-subscriptions-clob.polymarket.com",
]

# fallback (Cloudflare anycast) caso o DoH falhe
FALLBACK = ["104.18.34.205", "172.64.153.51", "104.18.35.205"]

_resolved = {}
_orig_getaddrinfo = socket.getaddrinfo


def _doh(host):
    url = "https://1.1.1.1/dns-query?name=%s&type=A" % host
    req = urllib.request.Request(url, headers={"accept": "application/dns-json"})
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=8, context=ctx) as r:
        data = json.loads(r.read().decode())
    ips = [a["data"] for a in data.get("Answer", []) if a.get("type") == 1]
    return ips


def resolve_all(verbose=True):
    for h in HOSTS:
        ips = []
        try:
            ips = _doh(h)
        except Exception as e:
            if verbose:
                print("[net] DoH falhou p/ %s (%s); usando fallback" % (h, e))
        if not ips:
            ips = FALLBACK
        _resolved[h] = ips
        if verbose:
            print("[net] %-45s -> %s" % (h, ", ".join(ips)))
    return _resolved


def _patched(host, port, *args, **kwargs):
    if isinstance(host, str) and host in _resolved:
        host = _resolved[host][0]
    return _orig_getaddrinfo(host, port, *args, **kwargs)


def install(verbose=True):
    resolve_all(verbose=verbose)
    socket.getaddrinfo = _patched
    return _resolved


def get_json(url, tries=3, timeout=20):
    last = None
    for _ in range(tries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            last = e
    raise last


if __name__ == "__main__":
    install()
    print(get_json("https://gamma-api.polymarket.com/markets?limit=1")[0]["slug"])
