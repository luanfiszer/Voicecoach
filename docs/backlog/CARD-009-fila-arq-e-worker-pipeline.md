# CARD-009 — Fila arq + worker com o pipeline do Turn

- **ID:** CARD-009 · **Épico:** Fase 1 — Fatia vertical
- **Plataforma:** backend · **Esforço:** M · **Status:** backlog
- **Dependências:** CARD-005, CARD-006, CARD-007, CARD-008

## Contexto

ADR-0005 (arq sobre Redis) e ADR-0003 (pipeline como passos componíveis —
costura para o V2). Este card mata o F3 do diagnóstico: o processamento sai
do request.

## Problema

As portas existem isoladas; falta o caso de uso que as compõe fora do ciclo
HTTP, com retry e transição de estado correta em falha.

## Proposta técnica

- `application/use_cases/process_turn.py`: orquestra
  `carrega Turn → STT → TeacherLlm → TTS → storage → completa Turn`, cada
  passo como função componível; falha em qualquer passo ⇒ `Turn.failed`
  com motivo tipado (não exceção engolida).
- Porta `TurnQueue` (`enqueue(turn_id)`); adapter arq.
- `worker/`: entrypoint arq registrando a task; retry limitado (ex.: 2) com
  idempotência — reprocessar um turn `completed` é no-op.
- Spans/logs estruturados por passo com `turn_id` (base da observabilidade
  da visão §D).
- Testes: use case com fakes de todas as portas (o teste central da
  arquitetura); integração fina do worker com Redis real.

## Escopo

- **In:** o acima. **Out:** endpoints HTTP (CARD-010); UsageEvent (CARD-014).

## Critérios de aceite

- **Dado** um Turn `pending` enfileirado, **quando** o worker processa,
  **então** o Turn fica `completed` com transcript e URL de áudio.
- **Dado** STT falhando (fake), **então** Turn fica `failed` com motivo e o
  retry respeita o limite.
- **Dado** um Turn já `completed` re-enfileirado, **então** nada é
  reprocessado (idempotência testada).
- **Dado** os fakes, **então** o teste do use case roda em milissegundos sem
  Redis/Postgres.

## Riscos

Sessão de banco dentro do worker (fora do ciclo request/Depends) — padrão de
sessão própria por job precisa ficar explícito para não vazar conexões.

## Objetivo de aprendizado

arq de ponta a ponta (enqueue, worker, retry, resultado) e o padrão "use case
como função de composição de portas" — o handler do CQS sem o MediatR, com
DI manual no worker (quem constrói o grafo fora do FastAPI).
