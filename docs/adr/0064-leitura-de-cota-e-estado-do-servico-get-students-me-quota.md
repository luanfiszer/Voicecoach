# ADR-0064 — A leitura de cota vira `GET /v1/students/me/quota`, sem cache, com o motivo do bloqueio explícito

- **Status:** aceito
- **Data:** 2026-09-13
- **Critério de obrigatoriedade** (`docs/adr/README.md`): **2 — define ou
  altera uma fronteira** (novo recurso público no contrato `/v1`, cujo nome e
  forma o próprio CARD-033 identifica como caro de reverter: *"o app web vai
  consumir o mesmo. Vale pensar o nome uma vez"*) e **5 — seria difícil de
  reverter** (renomear um recurso HTTP já consumido por clientes publicados
  custa mais que uma sessão de trabalho).
- **Relacionado:** ADR-0063 (o freio que esta leitura espelha), ADR-0007
  (autenticação adiada para a Fase 3), CARD-033, CARD-015

## Contexto

O CARD-015/ADR-0063 entrega o **freio** (recusa o `POST` quando a cota
estoura) mas nenhuma leitura responde *"quanto me resta?"* sem que o aluno
tente falar e seja recusado — três telas do design (chip da conversa, saldo do
perfil, paredes de quota/pausa) não têm de onde ler. O CARD-033 pede essa
leitura. Três decisões da implementação têm superfície de contrato ou custo de
reversão altos o bastante para registro:

1. **o nome e a forma do recurso** — é público, versionado sob `/v1` (ADR-0008:
   só evolução aditiva depois disso), e o app web vai consumi-lo também;
2. **se a leitura cacheia**, e com que TTL/gatilho (RNF2 do card exige
   resposta explícita, não "decide depois");
3. **como comunicar "meus minutos sobram, mas não posso falar"** (RF5) sem
   expor a mecânica interna de turns que o ADR-0063 decidiu não expor no
   `429`.

## Decisão

**1. `GET /v1/students/me/quota`.** `students` como coleção nova (não
pendurado em `sessions`, que é outra coleção); `me` no lugar de um id de
path — não há autenticação ainda (ADR-0007), então `me` resolve hoje para
`DEV_STUDENT_ID` (a mesma constante que `POST /sessions` já usa), e quando o
token existir, só a resolução de `me` muda — a URL que o app já chama
continua igual. Rejeita-se um path com o id do aluno explícito porque, sem
auth, ele seria adivinhável e não expressaria a intenção ("é sempre o
aluno autenticado, nunca um id arbitrário").

**2. Sem cache.** RNF2 do card pede TTL e gatilho, ou o registro de que não há
cache. As duas leituras que compõem a resposta (`totals_for_student` — uma
agregação por índice composto, CARD-014 — e `service_budget.is_exceeded` —
uma leitura Redis, ADR-0063) já são exatamente as que `POST /turns` paga em
todo turn aceito. Nenhuma é uma varredura. Cachear introduziria uma
**terceira fonte** para divergir da que o freio usa — o risco que o próprio
card mais teme (RNF3: *"se a tela disser 12 e o POST recusar no 11, o produto
mente"*) — para resolver um custo que o índice já resolve. Decisão: não
cachear; reavaliar só se a agregação aparecer como hot path em profiling
real.

**3. `blocked_reason` como campo explícito, com três valores** (`daily_minutes`
| `many_short_turns` | `service_paused`), **ao lado** de `spoken`/`quota_spoken`
em minutos — nunca substituindo-os. A tela sempre mostra a barra de minutos
correta (RF5: *"a leitura mostra só os minutos"*); o motivo do bloqueio é dito
à parte, em linguagem que não nomeia "teto de turns" (`many_short_turns` vira
a frase do produto, "você fez muitas falas curtas hoje" — a tradução para
copy fica com o CARD-027/tela, não com este contrato). Prioridade quando mais
de um morde ao mesmo tempo: `service_paused` (fato do produto) vence
`daily_minutes`, que vence `many_short_turns` — o serviço pausado é a
informação mais importante de todas, e esconder um teto de minutos batido
atrás de "muitas falas curtas" mentiria pela metade errada.

**4. Nunca expõe dinheiro** (RF4): nenhum campo do schema carrega
`estimated_cost_usd`, `daily_budget_usd` ou `monthly_budget_usd`. O contrato
só tem os dois fatos que o aluno tem direito de saber: quanto falou/quanto
pode, e se o serviço está disponível.

## Alternativas consideradas

### Alternativa A — pendurar em `GET /v1/sessions/{id}` ou devolver junto do `POST /turns`

Rejeitada: cota é um fato do **aluno através do dia**, não de uma sessão ou de
um turn — o chip da tela principal (artboard 01) precisa do saldo antes de
qualquer sessão existir. Acoplar ao ciclo de vida de sessão/turn obrigaria o
cliente a ter um turn em voo só para saber quanto lhe resta.

### Alternativa B — expor `remaining_turns` também, ao lado de `spoken`/`quota_spoken`

Rejeitada pelo próprio RF5: uma segunda barra de turns ao lado da de minutos
contradiz a decisão de produto de 2026-08-27 (comunicar só em minutos) e
vazaria a mecânica de custo por chamada que o ADR-0063 decidiu não comunicar.

### Alternativa C — cache com TTL curto (5–10s) e invalidação por evento

Tecnicamente viável (o gatilho óbvio seria "um turn entrou na fila"), mas
adiada: o RNF6 ("custo de leitura próximo de zero") já está satisfeito sem
cache, porque as duas queries subjacentes são as mesmas que o `POST` já paga.
Cache aqui compraria uma fonte extra de divergência (RNF3) para resolver um
problema de custo que não existe hoje.

## Consequências

- **Positivas:** uma fonte só para "o aluno pode falar?" em toda a API — a
  mesma que decide o `429`/`503` do `POST`; nenhuma tabela nova, nenhuma
  migration; o nome do recurso sobrevive à chegada da autenticação sem
  quebrar o cliente.
- **Negativas:** `blocked_reason` com três valores é uma pequena união fechada
  a manter sincronizada com a lógica de `StartTurnHandler` — um quarto motivo
  de recusa que nasça lá (se o produto criar um) tem de nascer aqui também, ou
  a leitura passa a mentir por omissão. Não há teste de tipo (`assert_never`)
  que force isso automaticamente, porque a leitura nunca falha — é vigilância
  de code review, registrada aqui para não ser esquecida.
- **Equivalente mental .NET:** um `GET` de leitura pura sobre o mesmo
  `IRateLimiter`/orçamento que o middleware de escrita já consulta — o
  paralelo mais próximo é uma Health Check customizada do
  `Microsoft.Extensions.Diagnostics.HealthChecks` que reusa os mesmos serviços
  injetados do pipeline, em vez de duplicar a leitura de estado.
