# CARD-015 — Quotas por conta + kill switch diário/mensal

- **ID:** CARD-015 · **Épico:** Fase 2 — Proteção de custo
- **Plataforma:** backend · **Esforço:** M · **Status:** backlog
- **Dependências:** CARD-010, CARD-014

## Contexto

ADR-0010: teto duplo (console Anthropic + aplicação). Diagnóstico §7.3:
quota é bloqueante antes de qualquer uso além do próprio autor. Lição do
F11: cobrar quota **só do que custa dinheiro**, no lugar certo do fluxo.

## Problema

Nada impede um loop descontrolado (bug do app, script) de gastar o orçamento
do mês em horas.

## Proposta técnica

- Quota diária por student em **segundos de áudio** (config, ex.: 600s/dia):
  verificada no POST do turn usando a duração real do upload; consumida
  **só quando o turn entra na fila** (F11: comando/erro de validação não
  consome).
- Kill switch global: contadores Redis `budget:daily` e `budget:monthly`
  (INCR de custo estimado ao completar turn + TTL de janela); excedido ⇒
  POST de turns responde `503` Problem Details "budget exhausted" até a
  janela virar.
- Rate limit por conta e por IP no POST (janela deslizante em Redis —
  a mecânica do protótipo, agora distribuída).
- **Duas janelas diferentes, de propósito** (ajuste do CARD-005, sessão de
  reconciliação): *rate limit* é janela deslizante; a **quota diária reseta por
  dia-calendário em fuso fixo** (a tela promete "renova às 00:00, horário de
  Brasília" — e um usuário que fala às 23h50 não pode ficar bloqueado até as
  23h50 do dia seguinte). A visão §D fala em "janela deslizante" para as duas
  coisas; a distinção é decisão deste card e provavelmente vira ADR. Os
  `TIMESTAMPTZ` do CARD-005 são o que torna essa conta possível.
- **Quota bloqueia escrita, não leitura**: com quota estourada, revisar as
  correções do dia continua liberado (a tela diz isso explicitamente). O bloqueio
  é do POST de turn, nunca do GET.
- Testes: estourar quota do student; estourar budget global; janela vira e
  libera; contagem atômica com requests concorrentes.

## Escopo

- **In:** o acima. **Out:** UI de "quota restante" no app (Fase 6); alertas
  externos (manual no console dos providers — ADR-0010).

## Critérios de aceite

- **Dado** um student no limite diário, **quando** envia turn, **então** 429
  Problem Details com `retry_after` indicando a virada da janela.
- **Dado** budget mensal excedido, **então** todo POST de turn responde 503
  honesto e `GET /health` continua 200.
- **Dado** 10 POSTs concorrentes perto do limite, **então** a contagem não
  ultrapassa (atomicidade testada).

## Riscos

Corrida entre verificação e consumo — resolver com operação atômica
(INCRBY + verificação no mesmo passo/Lua) em vez de get-then-set.

## Objetivo de aprendizado

Padrões atômicos de Redis (INCR/EXPIRE, quando um script Lua é necessário)
e a diferença entre rate limit, quota e budget — três mecanismos que o
protótipo misturava num só módulo.
