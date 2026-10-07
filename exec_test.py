"""Teste de EXECUCAO: compara nossos fills simulados com os fills REAIS do Anon.

Para cada fill real do Anon (mesmo token), procura nosso fill mais proximo no tempo.
Mede: taxa de coincidencia, dt medio e diferenca de preco.

Uso: python exec_test.py [pm.db]
"""
import sqlite3
import sys
import statistics
from collections import defaultdict

DB = sys.argv[1] if len(sys.argv) > 1 else "pm.db"
W = 20  # janela (s)

con = sqlite3.connect(DB)
la = [(r[0], r[1], r[2], r[3]) for r in con.execute("SELECT ts,token,price,size FROM la_fills")]
an = [(r[0], r[1], r[2], r[3], r[4]) for r in con.execute("SELECT ts,token,side,price,size FROM anon_fills")]
con.close()

antok = defaultdict(list)
for ts, tok, side, price, size in an:
    antok[tok].append((ts, price, side, size))
latok = defaultdict(list)
for ts, tok, price, size in la:
    latok[tok].append((ts, price, size))

print("nossos fills (LikeAnon): %d | fills REAIS do Anon: %d" % (len(la), len(an)))
print("tokens: nossos=%d | anon=%d | em comum=%d" % (
    len(latok), len(antok), len(set(latok) & set(antok))))

dts, dprices = [], []
matched = 0
for tok, lst in antok.items():
    las = sorted(latok.get(tok, []))
    if not las:
        continue
    for ats, ap, aside, asz in lst:
        near = [x for x in las if abs(x[0] - ats) <= W]
        if near:
            b = min(near, key=lambda x: abs(x[0] - ats))
            matched += 1
            dts.append(abs(b[0] - ats))
            dprices.append(abs(b[1] - ap))

if an:
    print("\n=== COINCIDENCIA (mesmo token, +/-%ds) ===" % W)
    print("fatura de match: %d / %d = %.1f%%" % (matched, len(an), 100 * matched / len(an)))
    if dts:
        print("dt medio: %.1fs | mediana: %.1fs" % (statistics.mean(dts), statistics.median(dts)))
        print("dpreco medio: %.4f (%.2f centavos) | mediana: %.4f"
              % (statistics.mean(dprices), 100 * statistics.mean(dprices), statistics.median(dprices)))
    else:
        print("sem matches ainda — deixe coletar mais.")
    # taxa por minuto
    if la and an:
        span = max([t[0] for t in la] + [t[0] for t in an]) - min([t[0] for t in la] + [t[0] for t in an])
        if span > 0:
            print("\ntaxa: nossos=%.2f/min | anon=%.2f/min  (span %dmin)"
                  % (len(la) / (span / 60), len(an) / (span / 60), span // 60))
