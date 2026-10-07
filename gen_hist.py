import json, statistics
rows=json.load(open(r"C:\Users\PROFIS~1\AppData\Local\Temp\mm_rows.json"))
rows.sort(key=lambda r: r["end"])
cum=0.0; eq=[]
for r in rows:
    cum+=r["pnl"]; eq.append(round(cum,2))
out={"equity":eq,"pnl":round(cum,2),"markets":len(rows),
     "winrate":round(100*sum(1 for r in rows if r["pnl"]>0)/len(rows),1),
     "avg":round(statistics.mean(r["pnl"] for r in rows),3),
     "roi":round(100*statistics.mean(r["pnl"]/r["cost"] for r in rows if r["cost"]>0),2),
     "title":"norm1e69 (historico 13.5h / 533 mercados)"}
json.dump(out, open(r"C:\Users\Profissional\Documents\projetos\jev\poli-mm\target_history.json","w"))
print("salvo:", out["pnl"], out["markets"], out["roi"], "%")
