# ADR-0074 — Contadores de custo são fail-closed; o custo por conta nova é uma view

- **Status:** aceito
- **Data:** 2026-10-01
- **Relacionado:** ADR-0010 (custo zero/teto), ADR-0016 (não persistir o derivável), ADR-0040 (Problem Details), ADR-0051 (custo congelado na escrita), ADR-0063 (cota, kill switch, rate limit), ADR-0069 (delete anonimiza), CARD-054
- **Critérios de obrigatoriedade:** **3 — custo recorrente** (o que acontece com o gasto quando o contador cai) e **2 — formato de dado persistido** (uma view nova no esquema).

## Contexto

O CARD-054 pede, como critério de aceite, que **Redis fora barre o turn** —
e avisa que é o oposto do reflexo usual de disponibilidade. Reproduzido pelo
gesto em 2026-10-01 (Redis parado com a API de pé): o turn já era barrado,
mas **por acidente** — o `RedisError` vazava cru e a API respondia
`500 text/plain`, contra o ADR-0040, e nada no código dizia que barrar era a
decisão. Um "conserto" bem-intencionado (capturar e deixar passar) seria
indistinguível de uma melhoria.

O mesmo card pede o custo por conta criada "consultável sem dashboard novo".

## Decisão

1. **`RateLimiterError` e `ServiceBudgetError` nas portas**, levantados pelos
   adapters Redis ao capturar `RedisError`, e listados em
   `FALHAS_DE_INFRAESTRUTURA` → `503 dependency-unavailable`. A docstring de
   cada erro diz que quem o recebe **barra**.
2. **Fail-closed vale para os contadores de custo**, não para todo Redis: o
   SSE (`TurnEvents`) continua com o seu recuo para polling (ADR-0026).
3. **`account_costs` é uma VIEW** sobre `students`, `usage_events` e
   `turn_translations`: turns e custo nos primeiros 7 e 30 dias de cada conta,
   com `has_unpriced_events` para custo desconhecido não virar zero.

## Alternativas consideradas

### A — Fail-open (Redis fora deixa passar)
- **Prós:** o produto não cai junto com o Redis.
- **Por que foi rejeitada:** libera custo sem contar, exatamente o que o
  contador existe para impedir. O próprio CARD-054 registra o preço aceito
  (Redis oscilando derruba o produto) e a mitigação (Redis local ao servidor).

### B — Custo por conta como tabela/coluna atualizada pelo worker
- **Por que foi rejeitada:** duplicaria o que `usage_events` já guarda e
  sairia de sincronia (ADR-0016). A view custa uma varredura por conta,
  irrelevante para uma consulta de operador.

### C — Endpoint administrativo ou script
- **Por que foi rejeitada:** não existe papel de admin na API, e um script
  é mais código para manter que uma view consultável por `psql`.

## Consequências

- Tradução já gravada e paga cujo `add_cost` falhe responde `503`; a próxima
  chamada a devolve do cache. Aceito: o custo não pode ser somado depois.
- Conta excluída sai da view depois do purge (o custo continua no total
  global de `usage_events`) — viés aceito pela anonimização do ADR-0069.
