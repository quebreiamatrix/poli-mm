import json
rows=json.load(open("miner_active.json"))
L=["# Carteiras ATIVAS mais consistentes — Polymarket","",
"Mineração da **fita de trades recentes** (quem está operando agora) + curva marcada",
"(`data-api/v2/user-pnl`, realizado+não-realizado = a curva do perfil). Gerado por `miner_active.py`.","",
"- **h1** = trades na última hora (500 = teto do fetch, ou seja gira ainda mais).",
"- **DD%** = drawdown máximo sobre o PnL (menor = mais 'reta pra cima').",
"- **dias** = tamanho do histórico; **up%** = % de dias positivos.","",
"**Rank: ativo agora + menor drawdown + consistência.**","",
"| # | Nome | Wallet | h1 | último | PnL $ | DD% | up% | dias | recovery |",
"|---|---|---|---|---|---|---|---|---|---|"]
for i,w in enumerate(rows,1):
    age = "agora" if w["age"]<=60 else "%dmin"%max(0,w["age"]//60)
    L.append("| %d | %s | `%s` | %d | %s | %.0f | %.1f | %.1f | %d | %.1f |"%(
        i, w["name"] or "—", w["addr"], w["h1"], age, w["final"], w["dd_pct"], w["upr"], w["days"], w["recov"]))
L+=["","## Links diretos (melhor → pior)",""]
for i,w in enumerate(rows,1):
    L.append("%d. %s — https://polymarket.com/profile/%s"%(i, w["name"] or w["addr"][:10], w["addr"]))
L+=["","## Destaques",
"- **Bots de arbitragem (mesma família do norm1e69):** #1 `0xD9E0AACa` (500 tr/h, DD 0.2%, 607 dias), #2 `0x99a093` (DD 0.2%, 272 dias), #9, #10, #18 — todos ~500 tr/h.",
"- **norm1e69** (o alvo) aparece em **#7** — confirma que é essa a lógica.",
"- **Mais retos:** #3 (98.5% dias+) e #4 `testBruno2` (97.3%).",
"","⚠️ São bots HFT/arb: consistência alta, mas copiar exige latência baixa (slippage come o edge)."]
open(r"C:\Users\Profissional\Documents\projetos\jev\carteiras-consistentes.md","w",encoding="utf-8").write("\n".join(L))
print("OK - MD gravado com", len(rows), "carteiras ativas")
