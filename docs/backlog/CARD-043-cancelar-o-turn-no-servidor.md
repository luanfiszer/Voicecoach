# CARD-043 — Cancelar o turn no servidor: o caminho que o V2 vai cobrar caro

- **ID:** CARD-043
- **Épico:** Qualidade da conversa (briefing 2026-09-09, ponto 2 — lado do servidor)
- **Esforço:** M
- **Status:** backlog
- **Dependências:** CARD-042, ADR-0058, ADR-0003, ADR-0037, ADR-0051

## Contexto

Com o CARD-042, o cliente cala. O servidor continua: STT já rodou, o professor
está gerando, o TTS sintetiza e o S3 recebe trechos que ninguém vai ouvir.

A pergunta que o briefing mandou responder primeiro tem número: **US$ 0,002678
por turn** (CARD-014). São ~370 abandonos por dólar. **Em dinheiro, isto é
ruído** — e a decisão de cancelar mesmo assim foi tomada em 2026-09-09 com esse
número na mesa.

O motivo registrado no ADR-0058 não é econômico: o ADR-0003 item 2 afirma que o
`Turn` foi modelado para acomodar cancelamento **em preparação para o V2**, e
uma afirmação dessas ou é exercida ou apodrece. O V1 é onde ela sai barata — um
consumidor, um turn por vez, sem contenção.

**Se este card se mostrar maior que uma sessão, o recuo está escrito** no
ADR-0058, alternativa A: fazer só o CARD-042 e gastar os US$ 0,0027. O produto
não degrada; só gasta.

## Problema

Não existe forma de dizer ao worker que o resultado não interessa mais. O
`arq` não oferece `kill` de task, e ele estaria errado de qualquer modo: matar a
corrotina no meio deixaria trecho meio escrito no S3 e `UsageEvent` sem fechar.

## Proposta técnica

Decisão em **ADR-0058** (aceito).

1. **`POST /v1/turns/{id}/cancel`**, não `DELETE`: nada é apagado, e o produto
   já decidiu em 2026-08-27 (CARD-032) que não apaga nada.
2. **Idempotente por natureza.** Cancelar duas vezes é `200`. Cancelar um turn
   já `completed` é `200` e não faz nada — a corrida "terminou enquanto o dedo
   ia ao botão" é o caso **comum**, não o excepcional.
3. **Cooperativo.** A API marca a intenção; o worker verifica entre as etapas da
   cascata, que já é uma fila interna com um consumidor só (ADR-0037) e tem
   pontos naturais de verificação entre sentenças. O turn para no próximo ponto,
   **não** no instante do clique — e essa janela precisa de nome, porque vai
   aparecer em log.
4. **O que já foi gerado permanece**, com a retenção normal (ADR-0024), e o
   `UsageEvent` registra o consumo real até o corte (ADR-0051 congela o custo na
   escrita). Turn cancelado reportando custo zero mentiria no dashboard.
5. **O cliente dispara e segue.** Falhar no `cancel` não é erro visível: no pior
   caso o servidor termina um turn que ninguém ouve, que é o estado de hoje.
6. O estado novo toca três lugares que precisam de caso novo: derivação de etapa
   (ADR-0028), retomada por SSE (ADR-0041) e varredura de travados (CARD-025).

## Refinamento obrigatório — cache e limites

**Cache:** não se aplica.

**Endpoint:** `POST /v1/turns/{id}/cancel`. **Teto:** por conta, e generoso —
cancelar é barato para o servidor e o abuso realista é bug de cliente em laço,
não malícia. Proposta declarada: **30/min por conta**, na camada de aplicação
(a infraestrutura protege a máquina; aqui o que se protege é a lógica). Número
inicial é estimativa, recalibrada por métrica. **Autorização:** só o dono do
turn cancela — endpoint autenticado também precisa de regra, e "o id é difícil
de adivinhar" não é uma.

**Dependência externa:** o worker fala com Redis (marcação/observação da
intenção) e o banco é a fonte da verdade (ADR-0035). **Timeout:** o
`redis_connect_timeout` já existente. **Idempotente:** sim, por desenho (item
2). **Desfecho quando o outro lado está fora:** o `cancel` falha em silêncio
para o aluno — ele já parou de ouvir (CARD-042), e o custo do turn perdido é
US$ 0,0027. Degradar aqui é aceitável e está escrito.

## Escopo

- **In:** o endpoint com autorização e limite; o estado de cancelamento no
  `Turn` e a migration; os pontos de verificação na cascata do worker; o
  `UsageEvent` fechado com o consumo real; o disparo no cliente; os casos novos
  em derivação de etapa, retomada e varredura.
- **Out:** barge-in (V2, ADR-0003). Cancelar por queda de conexão — o ADR-0058
  alternativa C explica por que **cair e desistir são coisas diferentes**, e
  confundi-las transformaria toda ida ao background em perda de turn. Apagar
  áudio já gerado.

## Critérios de aceite

- **Dado** um turn em processamento, **quando** `POST /cancel` é chamado,
  **então** responde `200` e o worker para na etapa seguinte — verificado com o
  `UsageEvent` mostrando **menos** trechos de TTS que um turn completo do mesmo
  insumo.
- **Dado** um turn já cancelado, **quando** `/cancel` é chamado de novo,
  **então** `200` e nada muda.
- **Dado** um turn já `completed`, **quando** `/cancel` é chamado, **então**
  `200`, o turn continua `completed`, e nada é desfeito.
- **Dado** um turn de outra conta, **quando** `/cancel` é chamado, **então** o
  mesmo desfecho de "não é seu" que o resto de `/v1` já usa — sem vazar
  existência, e em Problem Details (ADR-0040).
- **Dado** um turn cancelado, **quando** o `UsageEvent` é lido, **então** ele
  registra o custo **realmente consumido** até o corte, e não zero.
- **Dado** um turn cancelado, **quando** a varredura de travados (CARD-025)
  roda, **então** ele **não** é tratado como travado.
- **Dado** o cliente com a rede fora, **quando** o aluno regrava, **então** ele
  cala do mesmo jeito e nenhum erro aparece na tela.

## Riscos

- **Escopo maior que uma sessão.** É o risco declarado, e o recuo está escrito
  no ADR-0058 (alternativa A). Se acontecer, o card é quebrado e o CARD-042
  entrega sozinho — o produto fica correto, só mais caro.
- **A janela entre "cliente calou" e "servidor parou"** vai confundir depuração
  se não for nomeada em log.
- **Um estado a mais no `Turn` toca três lugares.** Esquecer um deles produz bug
  sutil: turn cancelado aparecendo como travado, ou a retomada tentando
  continuar o que foi abandonado.

## Objetivo de aprendizado

Entender **cancelamento cooperativo em `asyncio`** e por que ele não é
`Task.Cancel()`: não há `CancellationToken` atravessando as chamadas, o `arq`
não mata task, e o que existe é uma flag observada entre etapas. A lição
transfere de .NET (lá também o cancelamento é cooperativo e depende de alguém
checar), mas o **ponto de checagem** aqui é decisão de desenho da cascata — e
descobrir onde ele cabe, sem deixar trecho meio escrito no S3, é o card.
