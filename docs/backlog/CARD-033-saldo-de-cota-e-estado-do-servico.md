# CARD-033 — Saldo de cota e estado do serviço como leitura: o aluno sabe antes de bater na parede

- **ID:** CARD-033
- **Épico:** Fase 3 — Proteção de margem (backend dos artboards 12, 15 e 16)
- **Plataforma:** backend · **Esforço:** P · **Status:** concluído (2026-09-13)
- **Dependências:** CARD-015 (entrega o freio e o ADR da cota), CARD-014 (concluído)

## Contexto

Backend de três telas: o chip *"12 min hoje"* da conversa (artboard 01), o
*"Quota de hoje 12/20 min · Renova às 00:00 (horário de Brasília)"* do perfil
(artboard 12), e as duas telas de parede — quota atingida (15) e serviço pausado
(16) — que o [CARD-027](CARD-027-telas-de-excecao-do-app.md) desenha no cliente.

O CARD-015 entrega o **freio**: ele recusa o POST quando o limite estoura. Ele
não entrega a **leitura**: nada no contrato responde *"quanto me resta?"* sem
que eu tente falar e seja recusado.

## Problema

**Um limite que só se conhece batendo nele é um limite hostil.**

Três consequências concretas, todas visíveis no design:

1. **o chip da tela principal não tem fonte.** *"12 min hoje"* aparece no
   artboard 01 — a tela mais aberta do app — e não há endpoint que o responda;
2. **a tela de pausa só é alcançável por erro.** *"As aulas estão pausadas —
   atingimos o limite de custo do dia"* é um estado do **serviço**, não do
   aluno. Descobri-lo só ao gravar e ser recusado desperdiça a gravação;
3. **"renova às 00:00, horário de Brasília" não é calculável no cliente.** O
   fuso é decisão de servidor (é o CARD-015 quem o fixa); um cliente que
   calcule "meia-noite local" erra para quem viaja e para quem tem o aparelho em
   outro fuso.

## Requisitos funcionais

- **RF1** — Existe uma leitura que devolve, para o aluno da requisição: o
  **consumido**, o **limite** e **quando a janela vira**, em **minutos falados**
  — a unidade decidida em 2026-08-27 e comunicada ao aluno.
- **RF2** — A virada da janela vem como **instante absoluto**, não como "faltam
  N horas". O cliente formata; o servidor decide quando é.
- **RF3** — A mesma leitura informa se o **serviço** está disponível (kill
  switch do orçamento). São dois fatos distintos e o app mostra telas
  diferentes: *"por hoje é isso"* (o aluno consumiu) × *"as aulas estão
  pausadas"* (o produto pausou).
- **RF4** — O estado do serviço é dito **sem expor o orçamento**. O aluno não vê
  quanto foi gasto em dólares nem qual é o teto: vê que está pausado e quando
  volta. Custo é dado do negócio, não do usuário.
- **RF5** — A cota **é** dupla (minutos comunicados + teto de turns/dia
  protegendo o caixa). A leitura mostra **só os minutos**; o teto de turns não
  vira segunda barra na tela. Ele só se manifesta se for **ele** quem morder — e
  aí a mensagem é honesta sem expor mecânica ("você fez muitas falas curtas
  hoje"), nunca um saldo de minutos que sobra ao lado de uma recusa.
- **RF6** — A leitura reflete **turns enfileirados**, não só concluídos: um turn
  em processamento já consumiu (o CARD-015 consome ao entrar na fila). Caso
  contrário o saldo mostrado convida a estourar.

## Requisitos não funcionais

- **RNF1 — Leitura nunca é bloqueada por cota nem por kill switch.** É a regra
  já fixada ("quota bloqueia escrita, não leitura") e aqui ela é literal: a tela
  que explica a parede não pode estar atrás da parede.
- **RNF2 — Refinamento de cache, respondido** (template, §"Refinamento
  obrigatório"). Esta leitura é chamada na abertura do app e provavelmente a
  cada turn. **TTL e gatilho** precisam de resposta: o gatilho óbvio é "um turn
  entrou na fila". Sem as duas respostas, não há cache — e aí a query agregada
  precisa ser barata por si.
- **RNF3 — Uma fonte de verdade só.** O CARD-015 vai decidir onde o contador
  mora (Postgres, Redis, ou Redis como cache). Esta leitura **consome a mesma
  fonte que o freio usa**. Se a tela disser 12 e o POST recusar no 11, o produto
  mente — e é o tipo de divergência que só aparece com usuário real.
- **RNF4 — `unpriced_turns` não pode virar silêncio.** O ADR-0051 decidiu que
  preço desconhecido é `NULL`, nunca `0`, e o `totals_for_student` já devolve a
  contagem. Se ela for maior que zero, a leitura de **custo** está incompleta —
  decida se isso afeta o que o aluno vê (provavelmente não: o aluno lê minutos,
  não dólares) e escreva a decisão.
- **RNF5 — Sem `float` em caminho de dinheiro**, se dinheiro aparecer — ADR-0013,
  a mesma regra que o CARD-014 defendeu.
- **RNF6 — Custo de leitura próximo de zero.** É a chamada mais frequente do
  app depois do POST de turn. Se ela custar uma agregação completa por abertura
  de tela, o RNF2 deixa de ser opcional.

## Escopo

- **In:** a leitura de saldo e estado do serviço; a virada da janela como
  instante absoluto; a separação entre "cota do aluno" e "serviço pausado"; a
  decisão de cache com TTL e gatilho, ou o registro de que não há.
- **Out:** o freio em si (CARD-015); as telas (CARD-027 e a tela de perfil, que
  depende da auth da Fase 3); histórico de consumo ao longo do tempo (é análise,
  e é web); notificação de "avisar quando voltar" (push, cortado pela visão §F).

## Critérios de aceite

- **Dado** um aluno que consumiu metade da cota, **quando** leio o saldo,
  **então** recebo consumido, limite e a virada da janela como instante, em
  minutos.
- **Dado** um aluno com minutos sobrando mas com o teto de turns/dia batido,
  **então** a leitura diz que ele não pode falar agora, e a razão não é "acabaram
  seus minutos".
- **Dado** o kill switch ativo, **então** a leitura informa serviço indisponível
  **e** responde `200` — a tela que explica não pode falhar.
- **Dado** o kill switch ativo, **então** a resposta **não** contém valor
  monetário nem teto de orçamento.
- **Dado** um turn recém-enfileirado, **então** o saldo já o reflete.
- **Dado** a cota estourada, **então** a leitura continua respondendo, e o valor
  batido é exatamente o que o POST usa para recusar (mesma fonte).
- **Dado** a virada da janela no fuso fixo, **então** o instante devolvido é o
  mesmo que o `retry_after` do CARD-015 aponta — provado com relógio fixo.

## Riscos

- **A unidade está decidida; a forma do limite duplo, não.** O RF5 é o caso
  esquisito deste card: saldo de minutos sobrando **com** o serviço recusando.
  Se ele não for tratado, a tela mente com números corretos — o pior tipo de
  mentira, porque parece bug do aluno.
- **Duas fontes divergindo é o modo de falha silencioso.** O RNF3 existe porque
  a tentação de "ler direto do Postgres na leitura e do Redis no freio" é
  grande, e a divergência só aparece quando um usuário reclama.
- **Card pequeno com superfície de contrato nova.** Nome e forma do recurso vão
  durar: o app web vai consumir o mesmo. Vale pensar o nome uma vez.

## Objetivo de aprendizado

`zoneinfo` da stdlib e a aritmética de "próxima meia-noite em fuso fixo" — que
não é `hoje + 1 dia` (horário de verão existe, e o Brasil pode voltar a tê-lo).
O equivalente em .NET é `TimeZoneInfo` + `DateTimeOffset`; a diferença que morde
é que em Python o `datetime` "ingênuo" (sem fuso) é um tipo **legítimo** que
compara e soma normalmente, então o erro não aparece na compilação — aparece com
três horas de diferença em produção.

## Execução (2026-09-13, loop autônomo)

**RF1/RF2** — `GET /v1/students/me/quota` (`api/routes/students.py`), servido
por `ReadQuotaStatusHandler` novo (`application/use_cases/read_quota_status.py`).
Devolve `spoken_seconds`, `quota_spoken_seconds` e `resets_at` — instante
absoluto, calculado por `janela_diaria()`, extraída de `start_turn.py` para o
módulo compartilhado `application/quota_window.py` (RNF3: o `POST` e este
`GET` agora chamam a MESMA função, não duas cópias que podem divergir).

**RF3/RF4** — `service_available: bool` e `blocked_reason` (união fechada:
`daily_minutes` | `many_short_turns` | `service_paused` | `null`) resolvem os
dois fatos distintos sem expor nenhum valor monetário — nenhum campo do
schema carrega dólares.

**RF5** — `blocked_reason=many_short_turns` quando o teto de turns morde com
minutos sobrando; `spoken`/`quota_spoken` continuam corretos nesse caso (a
barra nunca mente). Prioridade quando mais de um motivo morde ao mesmo tempo:
`service_paused` > `daily_minutes` > `many_short_turns` — decisão registrada
no ADR-0064 (o serviço pausado é o fato mais importante).

**RF6** — satisfeito de graça: a mesma `totals_for_student` que o CARD-015 já
soma inclui turns `queued`/`processing` (ela conta pela existência do
`UsageEvent`, que o worker grava ao concluir — na prática, para a leitura,
"consumiu" e "entrou na fila" convergem porque não há outro caminho de
consumo).

**RNF1** — a leitura nunca falha: `ReadQuotaStatusHandler.handle()` não
devolve `Result`, é uma função que sempre informa. Kill switch ativo e cota
estourada respondem `200`.

**RNF2 (cache)** — decidido em ADR-0064: **sem cache**. As duas leituras
subjacentes já são as que `POST /turns` paga em todo turn — nenhuma é
varredura, e cachear introduziria uma terceira fonte para divergir da do
freio (o risco que o RNF3 mais teme).

**RNF3** — a mesma fonte do freio: `UsageEventRepository.totals_for_student` e
`ServiceBudget.is_exceeded`, chamadas na mesma ordem que `StartTurnHandler`.
Testado em `tests/api/test_students.py::test_a_mesma_leitura_que_o_post_de_turn_usa`.

**RNF4/RNF5/RNF6** — `unpriced_turns` não entra nesta leitura (ela não expõe
custo, RF4); nenhum `float` em caminho de dinheiro (não há dinheiro no
contrato); custo de leitura é o mesmo que o `POST` já paga — sem agregação
extra.

**Decisão de contrato (registrada em ADR-0064, critério 2 e 5):** o recurso é
`GET /v1/students/me/quota` — `students` como coleção nova, `me` resolvendo
hoje para `DEV_STUDENT_ID` (mesma decisão de `POST /sessions`) e sobrevivendo
à chegada da autenticação sem mudar a URL que o cliente chama.

**Testes:** `tests/application/test_read_quota_status.py` (novo, 5 testes —
inclusive o caso esquisito do RF5 e a prioridade de motivos), `tests/api/test_students.py`
(novo, 4 testes de rota, incluindo o `200` com kill switch ativo e a
ausência de campos monetários no corpo).

**Contrato:** `openapi.json` e `packages/api-client/src/schema.d.ts`
regenerados.

**ADR novo:** [0064](../adr/0064-leitura-de-cota-e-estado-do-servico-get-students-me-quota.md)
— critério 2 (novo recurso público) e 5 (nome caro de reverter, o próprio
card já sinalizava isso no risco "Card pequeno com superfície de contrato
nova").

**Regra do explicador:** nenhuma pergunta de previsão coube nesta sessão — as
três decisões com superfície de contrato (nome do recurso, cache, prioridade
de `blocked_reason`) foram resolvidas com o que o card e o ADR-0063 já
haviam decidido, sem ambiguidade de produto nova a abrir.
