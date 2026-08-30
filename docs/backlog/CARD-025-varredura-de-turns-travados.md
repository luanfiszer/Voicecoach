# CARD-025 — Varredura de turns travados: o worker morto deixa de deixar o aluno esperando

- **ID:** CARD-025
- **Épico:** Fase 1 — Fatia vertical em cascata
- **Esforço:** P
- **Status:** concluído (2026-08-29, branch `card-025-varredura-de-turns-travados`)
- **Dependências:** CARD-009 (concluído); ADR-0023, ADR-0005
- **ADR produzido:** [ADR-0052](../adr/0052-o-retry-do-arq-e-explicito-e-a-marcacao-de-falha-mora-num-lugar-so.md)

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
- Query nova no `TurnRepository`: `list_stale(before, limit)` — **devolvendo
  ids, não entidades**, ao contrário do que este card previa. Uma lista de `Turn`
  é uma foto: entre o SELECT e o `update`, o worker pode ter concluído o turn, e
  gravar a foto escreveria `failed` sobre `completed` sem que `Turn.fail()`
  disparasse. Quem varre relê pelo `get` — e é lá que o eager load dos trechos é
  obrigação do repositório (ADR-0052, decisão 4).
- Para cada um: `turn.fail(motivo, now)` + `update` + `commit` + publicar
  `Failed` no canal (ADR-0035), **preservando os trechos** — um turn travado
  depois de duas frases entregues sai como `delivered_partially`.
- **A varredura roda no worker, não na API.**

> **CORRIGIDO NA EXECUÇÃO (2026-08-29).** Este item dizia que "um `cron_job` do
> arq com mais de uma réplica executa em todas". **É falso com o default.** O
> `unique=True` do `arq.cron` monta um `job_id` determinístico a partir do
> `next_run`, e o segundo `enqueue_job` é recusado pelo Redis. Medido com duas
> réplicas: **1 job** com o default, **2** com `unique=False`
> (`tests/worker/test_varredura_e_retry.py`). O arq coordena com a unicidade da
> chave o que o Quartz coordena com uma tabela de locks. O que ele **não**
> resolve: relógios fora de sincronia entre réplicas geram `next_run` distintos,
> logo ids distintos, logo duas execuções — inofensivo aqui, porque a varredura é
> idempotente.

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

> **CORRIGIDO NA EXECUÇÃO:** o fator `max_tries` **não existe**. O `arq` não
> retenta exceção comum, então `MAX_TRIES` nunca multiplicou nada (ADR-0052). A
> conta final está no `config.py`, junto do `stale_turn_after`.
- Prazo curto demais transforma lentidão em falha; longo demais mantém o
  problema. É a decisão central do card.

## Objetivo de aprendizado

`cron_jobs` do `arq` — como um scheduler embutido no worker difere de um
`IHostedService` com `PeriodicTimer`, e o que acontece com ele quando há mais de
uma réplica do processo (o problema que o `Quartz` resolve com cluster e o arq
não resolve sozinho).

---

## Execução (2026-08-29)

### O que este card encontrou antes de escrever a primeira linha

A investigação prevista no prompt (§3.3) achou um **segundo buraco, maior que o
original e com o mesmo sintoma**. `ProcessTurnHandler._tratar_falha` levantava a
exceção crua com o comentário *"devolvendo à fila"*. Medido contra o `arq` 0.28,
worker real e Redis real:

| Exceção levantada | Chamadas da função | `jobs_retried` |
|---|---|---|
| `RuntimeError` (comum) | **1** | 0 |
| `arq.Retry(defer=0)` | **2** (`job_try` 1, 2) | 2 |

Ou seja: o turn ficava `processing` **para sempre** pelo caminho *normal* de
falha, `MAX_TRIES = 2` limitava um contador que nunca passava de 1, e o ramo
`final` de `_tratar_falha` era código morto.

**Decisão do desenvolvedor (D1): corrigir com `Retry`.** O caso de uso levanta
`RetryableTurnFailureError` e a composition root do worker traduz em
`arq.Retry(defer=0)` — `application` não pode importar `arq` (ADR-0012).

### O que foi entregue

| Arquivo | O quê |
|---|---|
| `application/use_cases/fail_turn.py` | **novo** — `FailTurn` (a receita `fail` → gravar → publicar) e `publicar_tolerante` (a política do ADR-0035), num lugar só |
| `application/use_cases/sweep_stale_turns.py` | **novo** — o caso de uso da varredura, com `SweepReport` |
| `application/ports/repositories.py` | `TurnRepository.list_stale(before, limit) -> list[UUID]` |
| `adapters/persistence/repositories.py` | a query, com `coalesce(started_processing_at, created_at)` e `order_by` |
| `application/use_cases/process_turn.py` | `RetryableTurnFailureError`; `_marcar_falha` e `_publicar` passam a delegar |
| `worker/main.py` | `cron_jobs`, a task `sweep_stale_turns`, e a tradução `RetryableTurnFailureError → arq.Retry` |
| `config.py` | `stale_turn_after` (5 min, com a conta escrita) e `stale_sweep_batch_limit` (50) |

### Critérios de aceite — verificados no sistema real

Worker real, Postgres real, três turns inseridos à mão (dois parados há 10 min,
um parado agora). Antes:

```
                  id                  |   status   | trechos
--------------------------------------+------------+---------
 1053ac1f-…7826f2                     | queued     |       0
 daeb77af-…62833f7                    | processing |       2
 2b895ab1-…3b632c96d2d                | processing |       0
```

Log do worker na virada do minuto:

```
INFO:arq.worker:Starting worker for 2 functions: process_turn, cron:sweep_stale_turns
INFO:arq.worker:  1.00s → cron:sweep_stale_turns()
WARNING:…sweep_stale_turns:turn 1053ac1f-… encerrado pela varredura (parado desde antes de 2026-08-30T00:53:00…)
WARNING:…sweep_stale_turns:turn daeb77af-… encerrado pela varredura (parado desde antes de 2026-08-30T00:53:00…)
INFO:…sweep_stale_turns:varredura: 3 examinados, 3 encerrados, 0 ignorados
INFO:arq.worker:  0.09s ← cron:sweep_stale_turns ●
INFO:arq.worker:  1.01s → cron:sweep_stale_turns()      ← 2ª rodada: nada a fazer
```

Depois:

```
                  id                  |   status   |                    motivo                     | tem_failed_at | trechos
--------------------------------------+------------+-----------------------------------------------+---------------+---------
 2b895ab1-…3b632c96d2d                | processing |                                               | f             |       0
 daeb77af-…62833f7                    | failed     | o turno excedeu o prazo de processamento e fo | t             |       2
 1053ac1f-…7826f2                     | failed     | o turno excedeu o prazo de processamento e fo | t             |       0

   status   | count
------------+-------
 completed  |    93     ← nenhum tocado
```

- ✅ **`queued` além do prazo ⇒ `failed` com motivo e evento** — verificado acima
  e em `test_turn_queued_alem_do_prazo_vira_failed_com_motivo_e_evento`.
- ✅ **`processing` com dois trechos ⇒ `failed`, trechos preservados,
  `delivered_partially` verdadeiro** — os 2 trechos continuam na tabela; o teste
  olha a **coleção**, não só o status (ADR-0023 item 6).
- ✅ **`processing` dentro do prazo não é tocado** — `2b895ab1` segue `processing`.
- ✅ **`completed` nunca é considerado** — 93 intactos.

### O prazo, com a conta (D2)

Pior caso **legítimo** de um turn que ainda pode dar certo, escrito no
`config.py` junto do campo:

| Parcela | Valor | Origem |
|---|---|---|
| STT | 8 s | `max_turn_audio_duration` 120 s × RTF 0,067 (medicao-latencia §3.2) |
| Professor | 60 s | `teacher_timeout_seconds` 30 s × 2 tentativas do SDK |
| TTS | 4 s | `teacher_max_tokens` 700 ≈ 2.800 chars × RTF 0,024 (§9.1) |
| Encode + storage + commits | 5 s | ADR-0034 (122 ms medidos por chamada) |
| **Pipeline** | **77 s** | |

`stale_turn_after = 5 min` ≈ 3,9× os 77 s, com a folga cobrindo a espera na fila
(`MAX_JOBS = 1`, p50 de 2,34 s por turn — ADR-0047). **Não há fator de
retentativa do `arq` nesta conta**: ele não existe (ADR-0052).

Cron a cada minuto ⇒ detecção entre 300 s e 360 s.

### Duas réplicas de worker — o que acontece

Um `cron_job` do `arq` com `unique=True` (o default) enfileira com
`job_id = f'{name}:{to_unix_ms(next_run)}'`. As réplicas calculam o mesmo
`next_run`, montam o mesmo id, e o segundo `enqueue_job` é recusado pelo Redis:
**uma execução, não N**. Medido — 1 com o default, 2 com `unique=False`.

Limite conhecido: relógios fora de sincronia geram `next_run` distintos e,
portanto, duas execuções. Inofensivo, porque a varredura é idempotente — o turn
que a segunda rodada encontrar já estará `failed` e cairá no ramo que ignora.

### Gates

```
uv run ruff format --check src tests   → 113 files already formatted
uv run ruff check src tests            → All checks passed!
uv run mypy                            → Success: no issues found in 113 source files
uv run lint-imports                    → Contracts: 4 kept, 0 broken.
uv run pytest --cov --cov-fail-under=80 → 349 passed, 9 deselected · 92,83%
uv run coverage report --include="*/domain/*,*/application/*" --fail-under=90 → 99%
```

`sweep_stale_turns.py` e `fail_turn.py`: **100%** de cobertura.

**Os gates mordem — provado injetando a violação, não afirmado:**

- `list_stale` sem o `coalesce` (só `started_processing_at`): o turn `queued`
  **some** e os outros dois testes continuam verdes —
  `FAILED test_list_stale_acha_o_queued_que_o_worker_nunca_pegou`. Revertido:
  3 passed.
- `cron(..., unique=False)`: `E assert 2 == 1`. Revertido: passou.
- O `Protocol` mordeu sozinho ao acrescentar `list_stale` à porta: **29 erros de
  `mypy` em 7 arquivos**, todos "este dublê não satisfaz mais `TurnRepository`",
  antes de qualquer teste rodar.

### Item de ADR da DoD

Conferido contra a lista "Quando um ADR é OBRIGATÓRIO" de `docs/adr/README.md`:
aplica-se o **critério 2 — define ou altera uma fronteira**, duas vezes (a
marcação de falha muda de casa; nasce um tipo de contrato entre `application` e o
worker). Escrito: [ADR-0052](../adr/0052-o-retry-do-arq-e-explicito-e-a-marcacao-de-falha-mora-num-lugar-so.md).

### Regra do explicador

Uma pergunta foi feita **no ponto da decisão**, antes de qualquer código: *"um
job cuja função levanta `RuntimeError`: quantas vezes o `arq` chama a função — uma
ou duas?"*. Desfecho: **dispensada pelo desenvolvedor** (*"esquece explicador"*).
Registrada como dispensa, nunca como cumprida (LEARNING-0004). O experimento foi
executado assim mesmo, porque bloqueava o plano — e o resultado está acima.

Das quatro decisões que os ADRs não cobriam, o desenvolvedor respondeu **D1**
(corrigir com `Retry`); D2, D3 e D4 foram assumidas com a recomendação do agente,
declaradas antes da implementação e registradas neste card e no ADR-0052.

### Dívidas declaradas

| O quê | Gatilho / card |
|---|---|
| Janela de milissegundos entre o `get` e o `commit` (o `FOR UPDATE` recusado) | ADR-0052, alternativa D: reabrir se aparecer `ignorados > 0` com reclamação de aluno |
| A tradução `RetryableTurnFailureError → arq.Retry` some em silêncio se alguém apagar o `except` | mitigado pelos testes que contam as chamadas; não há gate estrutural |
| 1 + N queries na varredura | medição, não intuição — irrelevante com lote de 50 |
| A varredura não notifica quem já fechou o stream | por desenho: quem descobre é o `GET` (CARD-012/027) |
