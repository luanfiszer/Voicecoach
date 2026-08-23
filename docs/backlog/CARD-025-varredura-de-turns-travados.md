# CARD-025 — Varredura de turns travados: o worker morto deixa de deixar o aluno esperando

- **ID:** CARD-025
- **Épico:** Fase 1 — Fatia vertical em cascata
- **Esforço:** P
- **Status:** backlog
- **Dependências:** CARD-009 (concluído); ADR-0023, ADR-0005

## Contexto

Dívida herdada do CARD-005 e explicitamente autorizada a virar card próprio pelo
CARD-009 (*"se estourar, o corte é a varredura de travados"*). O card estourou o
suficiente para o corte valer.

## Problema

**Não há dono para o turn que ninguém terminou.** Hoje:

- um turn `queued` cujo worker nunca apareceu fica `queued` para sempre;
- um turn `processing` cujo worker morreu no meio fica `processing` para sempre.

O `Turn.fail()` já aceita a partir dos **dois** estados de propósito
(`domain/turn.py`), e `delivered_partially` já é derivado — a entidade está
pronta desde o CARD-018. O que falta é **quem chama**.

A consequência é de produto, não de higiene: o app fica na tela de espera sem
nada que a encerre. A tela de timeout existe no desenho e não tem o que a
alimente.

## Proposta técnica

- **Job periódico do `arq`** (`cron_jobs` no `WorkerSettings`), varrendo turns
  em `queued`/`processing` com `created_at` / `started_processing_at` além de um
  prazo configurável.
- Query nova no `TurnRepository` — provavelmente `list_stale(before, limit)`,
  com o mesmo cuidado de eager load dos trechos que o `list_by_session` do
  CARD-009 documentou.
- Para cada um: `turn.fail(motivo, now)` + `update` + `commit` + publicar
  `Failed` no canal (ADR-0035), **preservando os trechos** — um turn travado
  depois de duas frases entregues sai como `delivered_partially`.
- **A varredura roda no worker, não na API.** Um `cron_job` do arq com mais de
  uma réplica de worker executa em todas; hoje há uma só (`MAX_JOBS = 1`), mas o
  card deve escrever o que acontece quando houver duas.

## Escopo

- **In:** job periódico, query de turns travados, teste com relógio controlado.
- **Out:** retentativa automática do turn travado (o ADR-0037 e o CARD-009 já
  decidiram que reprocessar depois de entrega parcial é proibido); alerta ou
  notificação ao aluno (CARD-012).

## Critérios de aceite

- **Dado** um turn `queued` há mais que o prazo, **quando** a varredura roda,
  **então** ele fica `failed` com motivo e um evento `failed` é publicado.
- **Dado** um turn `processing` **com dois trechos** travado há mais que o
  prazo, **então** ele fica `failed`, os dois trechos **permanecem**, e
  `delivered_partially` é verdadeiro.
- **Dado** um turn `processing` **dentro** do prazo, **então** a varredura não o
  toca.
- **Dado** um turn `completed`, **então** a varredura nunca o considera.

## Riscos

- **Corrida com o worker vivo:** a varredura pode matar um turn que está
  demorando legitimamente (um turno longo, um provedor lento). O prazo tem de
  ser folgado em relação ao `teacher_timeout_seconds` × `max_tries`, e a conta
  precisa estar escrita, não estimada.
- Prazo curto demais transforma lentidão em falha; longo demais mantém o
  problema. É a decisão central do card.

## Objetivo de aprendizado

`cron_jobs` do `arq` — como um scheduler embutido no worker difere de um
`IHostedService` com `PeriodicTimer`, e o que acontece com ele quando há mais de
uma réplica do processo (o problema que o `Quartz` resolve com cluster e o arq
não resolve sozinho).
