"""Calibracao POR TOKEN: fator = taxa real do Anon / nossa taxa simulada, por token.

Le la_fills (nossos) e anon_fills (reais) do banco e gera calib_tok.json.
O backtest usa esse fator por token (em vez de um haircut global).

Uso: python calib_tok.py [pm.db]
"""
import json
import sqlite3
import sys
from collections import Counter

DB = sys.argv[1] if len(sys.argv) > 1 else "pm.db"
con = sqlite3.connect(DB)
our = Counter(r[0] for r in con.execute("SELECT token FROM la_fills"))
anon = Counter(r[0] for r in con.execute("SELECT token FROM anon_fills"))
con.close()

fac = {}
for tok, n in our.items():
    a = anon.get(tok, 0)
    fac[tok] = round(max(0.0, min(1.0, a / n)) if n else 0.0, 4)

json.dump(fac, open("calib_tok.json", "w"))
vals = [v for v in fac.values() if v > 0]
print("tokens:", len(fac), "| com fator>0:", len(vals),
      "| fator medio (dos>0): %.3f" % (sum(vals) / len(vals) if vals else 0.0))
