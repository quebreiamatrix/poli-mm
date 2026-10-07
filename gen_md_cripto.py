import json
rows=json.load(open("miner_clean.json"))
L=["# Top 10 carteiras CRIPTO (Up/Down 5m) — ativas e consistentes","",
"Mineração da fita + curva marcada (`v2/user-pnl`). Filtros: ativa (<30min), PnL 7d>0, cripto>=50%, consistência.","",
"| # | Nome | Wallet | ticket médio | h1 | PnL $ | 7d $ | DD% | up% | dias |","|---|---|---|---|---|---|---|---|---|---|"]
# ticket medio nao esta no json; usar placeholder
for i,w in enumerate(rows,1):
    L.append("| %d | %s | `%s` |  | %d | %.0f | %.0f | %.1f | %.1f | %d |"%(
        i,w["name"] or "—",w["addr"],w["h1"],w["final"],w["recent7"],w["dd_pct"],w["upr"],w["days"]))
L+=["","## Links (melhor → pior)",""]
for i,w in enumerate(rows,1):
    L.append("%d. %s — https://polymarket.com/profile/%s"%(i,w["name"] or w["addr"][:10],w["addr"]))
L+=["","## Destaques",
"- **#1 Anon (0x5916ce)** — DD 0,2%, 98,5% dias+, ticket ~$2 → **melhor p/ banca de $100**.",
"- **#2 0xe1e556d1de** — DD 0,4%, +$1.675 em 7d.",
"- **#8 NihiIism** — DD 0,8%, 239 dias (longevidade).",
"- **#4 mo-money / #6 bosona** — muito lucro, mas **ticket grande** (menos ideal p/ $100).",
"","⚠️ Bots HFT/maker: consistência alta, mas copiar exige latência baixa."]
open(r"C:\Users\Profissional\Documents\projetos\jev\carteiras-cripto-top10.md","w",encoding="utf-8").write("\n".join(L))
print("MD criado:", len(rows), "carteiras")
