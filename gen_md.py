import json
rows=json.load(open("miner_top.json"))
L=[]
L.append("# Carteiras mais consistentes — Polymarket (curva marcada)\n")
L.append("Fonte: `data-api.polymarket.com/v2/user-pnl` (economic_pnl = realizado+não-realizado),")
L.append("a MESMA curva do gráfico do perfil. Minerado por `miner.py`.\n")
L.append("Rank: **menor drawdown % + consistência + lucro**.\n")
L.append("| # | Nome | Wallet | PnL $ | maxDD $ | DD% | dias | up% | recovery |")
L.append("|---|---|---|---|---|---|---|---|---|")
for i,w in enumerate(rows,1):
    L.append("| %d | %s | `%s` | %.0f | %.0f | %.1f | %d | %.1f | %.2f |"%(
        i,w["name"],w["addr"],w["final"],w["maxdd"],w["dd_pct"],w["days"],w["upr"],w["recovery"]))
L.append("\n## Links diretos\n")
for i,w in enumerate(rows,1):
    L.append("%d. %s — https://polymarket.com/profile/%s"%(i,w["name"] or w["addr"][:10],w["addr"]))
L.append("\n> DD%=0,0 exato pode ser suavização do grid diário — **conferir no gráfico do perfil**.\n")
open(r"C:\Users\Profissional\Documents\projetos\jev\carteiras-consistentes.md","w",encoding="utf-8").write("\n".join(L))
print("MD atualizado com",len(rows),"carteiras")
