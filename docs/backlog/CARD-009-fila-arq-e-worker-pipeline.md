# CARD-009 — Worker em cascata, com modelos residentes e o caminho triste da entrega parcial

- **ID:** CARD-009 · **Épico:** Fase 1 — Fatia vertical em cascata
- **Plataforma:** backend · **Esforço:** **G — candidato a quebra** · **Status:** backlog
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
