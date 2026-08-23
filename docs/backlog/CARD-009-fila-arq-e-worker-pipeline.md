# CARD-009 — Worker em cascata, com modelos residentes e o caminho triste da entrega parcial

- **ID:** CARD-009 · **Épico:** Fase 1 — Fatia vertical em cascata
- **Plataforma:** backend · **Esforço:** **G — candidato a quebra** · **Status:** **concluído** (2026-08-23), sem quebrar em dois
- **Dependências:** CARD-018, CARD-006, CARD-007, CARD-008; ADR-0023, ADR-0025

## Contexto

ADR-0005 (arq sobre Redis), [ADR-0025](../adr/0025-modelos-residentes-no-worker-e-readiness-que-distingue-pronto.md)
(modelos residentes) e ADR-0003, cuja **costura 4** é exatamente o que este card
cobra: *"pipeline como passos componíveis — o V2 rearranja os mesmos passos em
modo streaming"*.

## Por que agora

É onde o alvo de 1,8 s deixa de ser soma de componentes e vira número real. Duas
coisas medidas se decidem aqui e **não** são ajustáveis depois:

1. **Cascata, não cadeia.** Uma cadeia `STT → LLM → TTS` sequencial entrega em
   ~4,1 s por construção. A cascata consome o `AsyncIterator` do CARD-007 e
   dispara o TTS por sentença — mesma composição, forma diferente.
2. **Modelos residentes.** Carregar por job custa **~6 s** (0,42 s de STT +
   5,63 s do Kokoro) — mais que todo o resto do turn somado.

## Problema

As portas existem isoladas; falta o caso de uso que as compõe fora do ciclo
HTTP. E o caminho triste ficou **qualitativamente** mais difícil: falhar depois
de o aluno já ter ouvido duas frases não é o mesmo que falhar antes de ele ouvir
qualquer coisa.

## Proposta técnica

- `application/use_cases/process_turn.py`, como **cascata**:

  ```
  carrega Turn → STT → async for evento in teacher.respond_streaming(history):
        SpokenSentence → TTS → storage.put(chunk) → turn.append_audio_chunk() → publica
        FeedbackReady  → persiste feedback → publica
  → concatena full → turn.complete() → publica
  ```

  Cada passo continua função componível; o que muda é o laço.
- **A síntese da sentença N+1 não espera o envio da N.** É o único paralelismo
  que este card introduz, e é onde mora o "custo de composição" que a medição
  §1 avisou não estar medido: contenção de CPU entre STT e TTS, GIL, cópia de
  áudio entre etapas.
- **Modelos no `on_startup` do `arq`** populando o `ctx` (ADR-0025). Nenhuma
  task constrói modelo. O worker publica `voicecoach:worker:ready` em Redis
  depois da carga, com TTL e heartbeat.
- **Medir a carga do adapter ativo e registrar** — a do `mlx-whisper` nunca foi
  cronometrada em separado (ADR-0025, item 7).
- Porta `TurnQueue` (`enqueue(turn_id)`); adapter arq.
- **Publicação dos eventos**: o worker escreve num canal Redis (pub/sub ou
  stream) que o endpoint SSE do CARD-010 consome. O worker **não** conhece HTTP.
- **Caminho triste, explícito** (ADR-0023 + ADR-0017):
  - falha **antes** do primeiro trecho ⇒ `Turn.fail(reason)`, cliente vê `failed`
    e pode reenviar;
  - falha **depois** ⇒ `Turn.fail(reason)` com os trechos **preservados**;
    `delivered_partially` é derivado; o cliente recebe `failed` com o que já
    tocou intacto. O aluno ouviu — o registro não pode dizer que não;
  - **retry só é permitido antes do primeiro trecho.** Reprocessar um turn que
    já emitiu áudio faria o professor recomeçar a falar. Retry limitado (2),
    idempotente, e turn `completed` re-enfileirado é no-op.
- **O Turn travado ganha dono** (dívida herdada do CARD-005): job periódico do
  arq varre turns em `queued`/`processing` além do prazo e chama `fail()`. Sem
  isso, worker morto deixa o aluno esperando para sempre.
- Logs estruturados e span por passo com `turn_id`, carregando o instante de
  cada trecho — é a fonte da métrica de produto (quando o aluno pôde ouvir a
  primeira palavra).

## Escopo

- **In:** use case em cascata, adapter de fila, worker com modelos residentes,
  publicação de eventos, caminho triste, varredura de travados, testes.
- **Out:** endpoints e SSE (CARD-010); `UsageEvent` (CARD-014); quotas
  (CARD-015).

## Critérios de aceite

- **Dado** um Turn enfileirado, **quando** o worker processa, **então** o
  primeiro trecho de áudio é gravado **antes** de o JSON do professor fechar
  (verificável pelos timestamps do trecho vs. `replied_at`).
- **Dado** dois jobs seguidos, **então** o segundo **não** paga carga de modelo
  (tempo medido no teste, com margem) — o critério que o ADR-0025 existe para
  garantir.
- **Dado** o worker subindo, **então** `voicecoach:worker:ready` só existe
  depois da carga, e o job não é consumido antes.
- **Dado** o TTS falhando na 3ª sentença, **então** o Turn fica `failed`, os 2
  trechos anteriores permanecem em storage e no banco, e nenhum retry acontece.
- **Dado** o STT falhando, **então** `failed` com motivo e retry respeitando o
  limite.
- **Dado** fakes de todas as portas, **então** o teste do use case roda em
  milissegundos sem Redis/Postgres — inclusive o fake do `TeacherLlm`, que
  agora é um gerador assíncrono.
- **Medição ponta a ponta registrada no card**: tempo até o primeiro trecho
  gravado, com o pipeline real.

## Riscos

- **Contenção de CPU** entre STT e TTS no mesmo processo. Se aparecer, o
  primeiro remédio é o `mlx-whisper` (que usa a GPU e libera a CPU — ADR-0027),
  não mais processos.
- Sessão de banco dentro do worker (fora de `Depends`): padrão de sessão por job
  precisa ser explícito para não vazar conexão.
- Card grande. Se estourar, o corte é a varredura de travados (vira card
  próprio) — **nunca** a cascata nem a residência dos modelos.

## Objetivo de aprendizado

`arq` de ponta a ponta (enqueue, `on_startup`, `ctx`, retry) e o consumo de
gerador assíncrono numa composição — o handler de CQS sem MediatR, com DI manual
fora do FastAPI, e o ciclo de vida de singleton num host de background service.


---

## Execução (2026-08-23)

Branch `card-009-worker-em-cascata`, a partir de `8635181`. O card **não** foi
quebrado em dois: a parte B (worker `arq` real, `ctx`, readiness) coube junto da
parte A. O que saiu de escopo está na seção de dívidas.

### Decisões levadas ao desenvolvedor antes da primeira linha

Três, como a governança do prompt de sessão exigia:

| Decisão | Escolha |
|---|---|
| Canal worker→API (pub/sub, Streams ou nada) | **pub/sub com payload completo**, banco como fonte da verdade → [ADR-0035](../adr/0035-canal-worker-api-por-pubsub-com-o-banco-como-fonte-da-verdade.md) |
| Histórico do professor | **incluir `list_by_session`** → [ADR-0036](../adr/0036-o-primeiro-consumidor-revela-o-que-faltava-nas-portas.md), item 4 |
| Dockerfile do worker | **card próprio** (dívida abaixo) |

**Um achado mudou a recomendação do canal antes de ela ser feita:** o evento
`feedback` do ADR-0026 carrega `{has_mistakes, original, corrected, tip}`, e
**nada disso é persistido** até o CARD-013. A leitura "canal nenhum, o SSE lê do
banco" — que o prompt de sessão considerava a mais fiel aos ADRs — não consegue
entregar um dos cinco eventos do contrato. Está registrado como alternativa
**descartada por evidência** no ADR-0035.

### O que entrou

**`application/` — o primeiro caso de uso do projeto**

- `use_cases/process_turn.py` — a cascata: `async for` sobre o professor, TTS por
  sentença, fila interna, gravação em ordem, caminho triste.
- `ports/turn_queue.py`, `ports/turn_events.py`, `ports/audio_encoder.py` — três
  portas novas.
- `ports/media_storage.py` ganha `get`; `ports/speech_to_text.py` ganha
  `SttError`; `ports/repositories.py` ganha `list_by_session` e `UnitOfWork`.

**`adapters/`** — `queue/arq_turn_queue.py`, `events/redis_turn_events.py`,
`readiness_keys.py`, `AacAudioEncoder` em `tts/encoding.py`, `S3MediaStorage.get`,
`SqlAlchemyTurnRepository.list_by_session`, `check_worker` no health.

**`worker/`** — `main.py` (composition root, `on_startup`/`on_shutdown`, `ctx`,
entrypoint `voicecoach-worker`) e `readiness.py` (chave + heartbeat). O diretório
tinha só `__init__.py` havia quatro cards.

**Testes** — `tests/fakes_pipeline.py` (dublês das **nove** portas),
`tests/application/test_process_turn.py` (23), `tests/adapters/test_turn_events.py`,
`tests/adapters/test_arq_turn_queue.py`, `tests/worker/test_readiness.py`,
`tests/worker/test_worker_lifecycle.py`, `tests/worker/test_pipeline_integracao.py`
(`slow`, gasta dinheiro).

### Critérios de aceite, um a um, com evidência

| Critério | Desfecho | Evidência |
|---|---|---|
| 1º trecho gravado **antes** de `replied_at` | ✅ | `test_o_primeiro_trecho_e_gravado_antes_de_replied_at`; e no pipeline real (§10.2 da medição) |
| 2 jobs seguidos, o 2º sem carga | ✅ **com o critério recalibrado** | ver abaixo |
| `voicecoach:worker:ready` só depois da carga | ✅ | `test_a_chave_de_prontidao_e_gravada_depois_de_toda_a_carga` + `test_o_arq_nao_consome_job_antes_de_o_startup_retornar` |
| TTS falha na 3ª ⇒ `failed`, 2 trechos vivos, sem retry | ✅ | `test_tts_falhando_na_terceira_preserva_os_dois_trechos_anteriores` |
| STT falha ⇒ `failed` com motivo, retry no limite | ✅ | dois testes: devolve à fila com tentativa restante, marca `failed` na última |
| Fakes de todas as portas, sem Redis/Postgres, em ms | ✅ | `48 passed in 0.13s` em `tests/application` |
| Medição ponta a ponta registrada | ✅ | `docs/medicao-latencia.md` §10 |

**A margem do "dois jobs seguidos", recalibrada e justificada.** O card pedia
"tempo medido, com margem". Com o Kokoro a diferença entre pagar e não pagar a
carga era de ~6 s — impossível de confundir com ruído. Com o Piper ela caiu para
~1 s (ADR-0032), e um limiar de tempo mal calibrado passaria por acidente num dia
de máquina rápida. **O critério virou contagem de construções, não tempo:**
`test_dois_jobs_seguidos_carregam_o_modelo_uma_vez_so` assere
`fabricas["stt"].chamadas == 1`. É o mesmo critério sem margem para errar — duas
chamadas seriam a regressão, uma é a decisão do ADR-0025.

### Gates

```
$ uv run ruff format --check src tests      →  All checks passed
$ uv run ruff check src tests               →  All checks passed
$ uv run mypy                               →  Success: no issues found in 88 source files
$ uv run lint-imports                       →  Contracts: 4 kept, 0 broken
$ uv run pytest --cov --cov-fail-under=80   →  216 passed, 9 deselected
                                               Total coverage: 92.31%
$ uv run coverage report --include="*/domain/*,*/application/*" --fail-under=90
                                               TOTAL 472 stmts, 0 miss → 99%
```

Núcleo **99%** (piso 90), global **92,31%** (piso 80). Suíte de 165 → **216**.

**O gate mordeu de verdade duas vezes nesta sessão, e uma delas era bug meu:**

1. Par completo provado de propósito, com `from arq.jobs import Job` injetado em
   `application`: `arq` **fora** da lista → `3 kept, 1 broken` (só `layers`);
   **dentro** → `2 kept, 2 broken`. A lista é o que enxerga biblioteca externa.
2. **Violação real, não injetada:** o `check_worker` do health importava
   `READY_KEY` de `voicecoach.worker.readiness`, e `adapters` não pode importar
   `worker` — `voicecoach.adapters.health -> voicecoach.worker.readiness (l.125)`.
   Conserto: a chave virou `adapters/readiness_keys.py`, módulo que os dois
   processos podem importar, pelo mesmo motivo que `PROCESS_TURN_TASK` mora no
   adapter de fila.

### Item de ADR da DoD — conferido contra `docs/adr/README.md`

Quatro ADRs, com o critério citado (LEARNING-0003):

- **[ADR-0035]** canal worker→API — **critério 2** (fronteira entre dois processos
  e formato do que trafega).
- **[ADR-0036]** as cinco extensões de porta — **critério 2** (cinco fronteiras).
- **[ADR-0037]** a forma da cascata — **critério 5** (difícil de reverter: vira
  contrato quando houver consumidor, e o modo de falha é intermitente).
- **[ADR-0038]** `arq` entra e rebaixa o `redis` — **critério 1** (dependência
  externa, e a entrada **remove** a versão de outra já existente).

Dívida do **ADR-0025, item 7** (carga do `mlx-whisper`) fechada com número medido,
e o item riscado no próprio ADR.

### O gatilho do `Result` (ADR-0017) — conferido, e NÃO atingido

O ADR-0017 deixou `Result` como TBD com gatilho escrito: *"o primeiro desfecho que
é normal do negócio e não bug"*. Foram inventariados todos os desfechos de falha
deste card:

| Desfecho | Natureza |
|---|---|
| STT / TTS / professor / storage caem | infraestrutura → exceção, decisão já tomada |
| professor devolve fluxo sem sentença falável | provedor fora do contrato → infraestrutura |
| turn re-enfileirado já `completed` | **no-op**, não é desfecho de falha |
| reprocessamento depois de trecho entregue | guarda de orquestração → `fail()` direto |
| turn ou session inexistente | divergência de banco → levanta |

**Nenhum é "normal do negócio e não bug".** Quota estourada é CARD-015,
`Idempotency-Key` é CARD-010. O gatilho **não** foi atingido, e inventar `Result`
aqui seria antecipação — registrado por escrito, que é a diferença entre decisão
e esquecimento.

### Regra do explicador — 1 de 2 fechada, e o padrão continua

Duas perguntas, ambas feitas **no ponto da decisão, antes do código**, ambas sobre
consequência observável, ambas conferidas rodando o comando na hora.

**Pergunta 1 — o encoder e a cadeia indireta do `forbidden`.** *"Se eu importar
`to_aac` do caso de uso, o que o `lint-imports` faz?"* Resposta: **"quebra 1
contrato"**. Executado: **2 contratos** — `layers` pela seta que sobe e
`forbidden` porque a cadeia `use_case → encoding → av` alcança `av`, com a rota
impressa no relatório. Explicado o mecanismo (o `forbidden` segue cadeias
indiretas, não só imports diretos) e **reformulado uma vez**, sobre a mesma
mecânica: *"tipar a porta de fila com `arq.jobs.Job` quebra quantos?"* Resposta:
**"2"**. Executado: **1** (`3 kept, 1 broken`) — o `layers` só enxerga o grafo
interno, e `arq` é externo. **Desfecho: EM ABERTO** (dívida). A reformulação que a
regra permite já foi usada; não fecho o item com explicação minha
(LEARNING-0004). Entra em `docs/perguntas-em-aberto.md` como **Q12**.

**Pergunta 2 — a forma da cascata.** *"`create_task` por sentença, com a 2ª
terminando antes da 1ª: o que acontece?"* Resposta: **`OutOfOrderAudioChunkError`**
— **correta** para a forma do código real, que tem dois `await` entre ler o índice
e gravar. A execução acrescentou o que a pergunta não previa: o erro só aparece
quando duas sínteses terminam no **mesmo instante**; quando não empatam, não há
exceção nenhuma e os trechos gravam densos **na ordem errada**. **Desfecho:
RESPONDIDA.**

**Q7, Q9 e Q11 foram reapresentadas na abertura** e **não foram respondidas nem
dispensadas** — o desenvolvedor respondeu apenas as três decisões de escopo.
Silêncio não é dispensa: seguem abertas.

**É a quinta sessão seguida.** A proposta de postmortem sobre a *regra* (não sobre
a sessão) foi feita na abertura e também ficou sem resposta. O CLAUDE.md pede o
postmortem; ele **não foi escrito** nesta sessão porque a decisão de reescrever
uma regra da constituição é do desenvolvedor. Fica como pendência de topo.

### Dívidas registradas

| Dívida | Gatilho / card |
|---|---|
| **Dockerfile do worker** | card próprio; decidido na abertura |
| **Varredura de turns travados** (job periódico do arq) | card próprio; o card já autorizava o corte |
| **Evento `feedback` não é retomável** por `Last-Event-ID` | CARD-013 (persistir correções) — ADR-0035, consequência negativa |
| **Composição em x86 com `faster-whisper` não medida** | a contenção de CPU que a §10.3 supõe ausente é justamente o que aconteceria lá |
| **Pickup da fila não medido** (`enqueue` → início do job) | o teste `slow` chama o caso de uso direto |
| **`type: ignore[no-untyped-call]` no `check_redis`** | `arq` aceitar `redis>=6` (ADR-0038) |
| **`asyncio.Queue` sem `maxsize`** | V2, ou qualquer mudança que faça o produtor emitir dezenas de itens (ADR-0037) |
| **ADRs 0024–0029 e 0035–0038 não destilados na skill** | a skill cobre 0001–0023 e 0030–0034; item de governança herdado |
| **`UsageEvent`, quotas, SSE, endpoints** | fora de escopo por desenho: CARDs 010, 014, 015 |
