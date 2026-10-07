# poli-mm — Shadow Market Maker (DRY)

Mede se o **nosso** mercado-maker automático reproduz a lógica da carteira
`norm1e69`: cota **bids nos dois outcomes** em torno do preço justo, é
preenchido por takers, mantém o livro ~neutro e carrega até a liquidação,
capturando o spread (~2–3%).

**Não envia ordem nenhuma.** Lê o WebSocket de mercado real da Polymarket e
**simula** os nossos fills. O objetivo é medir — não operar dinheiro.

## Rodar

```bash
python app.py          # abre http://localhost:8800
```

Só depende de `websockets` (`pip install websockets`).

## O que ele faz

- **Bypass de DNS via Cloudflare** (`net.py`): o DNS local bloqueia a
  Polymarket; resolvemos via DoH em `1.1.1.1` e forçamos `socket.getaddrinfo`
  a usar os IPs da Cloudflare (TLS/SNI continua com o hostname certo).
- Descobre os mercados `{btc,eth,sol}-updown-5m-<unix>` da janela corrente.
- Assina o WS `wss://ws-subscriptions-clob.polymarket.com/ws/market` e mantém
  o livro ao vivo (`book` / `price_change`) e os trades (`last_trade_price`).
- **Cota** um bid no `best_bid` de cada outcome (só em mercado "vivo", mid
  0.15–0.85), respeitando uma latência (`LATENCY_MS`).
- **Fill:** quando um trade com `side == SELL` (agressor vendeu) imprime em
  preço `<=` ao nosso bid, contamos fill no nosso preço.
- Na virada da janela, liquida pelo `winner` real (`clob /markets/{id}`) e
  calcula PnL por mercado.

## Parâmetros (`app.py`)

| param | default | o que é |
|---|---|---|
| `QUOTE_SIZE` | 30 | shares por bid |
| `LATENCY_MS` | 300 | atraso até o quote "estar no livro" |
| `MAX_SHARES_PER_TOKEN` | 400 | teto de inventário por lado |
| `MIN_MID`/`MAX_MID` | 0.15/0.85 | só cota em mercado não-decidido |
| `ASSETS` | btc,eth,sol | ativos |
| `DURATION` | 5m | janela |

## Leitura do painel

- **Spread médio** = `mid − preço_do_fill`, média ponderada. Alvo do alvo
  (`norm1e69`) ≈ 2–3% por mercado.
- **Inv** por lado: se ficar muito assimétrico, o modelo não está neutro.
- `*` ao lado do quote = ainda em latência (não está no livro).

## Limitações honestas

1. **Fill otimista:** assumimos que entramos quando o preço toca o bid; na
   vida real há fila na frente. O nº de fills é um **teto**.
2. Não modela taxa ainda (maker na Polymarket tende a 0, mas confirmar).
3. `data-api` (REST) tem lag de indexação — por isso usamos o **WS**.

## Próximos passos

- Modelar fila (prioridade) e taxa para fills realistas.
- Calibrar o preço do quote (hoje = `best_bid`) e a neutralidade.
- Comparar, no mesmo painel, nosso PnL vs o da carteira alvo.
