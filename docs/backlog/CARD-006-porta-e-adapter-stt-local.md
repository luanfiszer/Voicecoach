# CARD-006 — Porta SpeechToText + adapters `mlx-whisper` e `faster-whisper`

- **ID:** CARD-006 · **Épico:** Fase 1 — Fatia vertical em cascata
- **Plataforma:** backend/IA · **Esforço:** M · **Status:** backlog
- **Dependências:** CARD-001; ADR-0027

## Contexto

ADR-0011 (STT local por default) e [ADR-0027](../adr/0027-adapter-duplo-de-stt-com-default-resolvido-pela-plataforma.md),
que fechou a avaliação que o ADR-0011 tinha pedido por escrito: `mlx-whisper` é
**~2× mais rápido** que `faster-whisper` no `small.en` (1,18 → 0,59 s), e é
**Apple Silicon apenas**. Não é trocar o default — é ter dois adapters.

Esta é a primeira porta real do sistema e a primeira vez que a fronteira do
ADR-0003 é exercitada com **duas implementações de verdade**.

## Por que agora

O STT é a primeira etapa do caminho de ~1,8 s e custa **0,59 s** dele — um
terço do orçamento, não um detalhe. Nada do resto pode ser medido enquanto ele
não existir, e o CARD-009 precisa dele residente no worker.

## Problema

Não existe adapter de IA nenhum no repositório. E a escolha ingênua
(`faster-whisper` com `int8`, `beam_size=5`, porque é o que os tutoriais
mostram) é **3× mais lenta** que a configuração medida como melhor.

## Proposta técnica

- `application/ports/speech_to_text.py`: `Protocol` com
  `transcribe(audio: AudioInput) -> Transcript`. Tipos próprios — nenhum tipo
  de biblioteca vaza pela porta.
- `adapters/stt/faster_whisper_adapter.py` e
  `adapters/stt/mlx_whisper_adapter.py`, com os defaults **medidos**:
  `float32` (não `int8` — medição §3.2: `int8` é mais lento neste hardware),
  `beam_size=1`, língua forçada `en`.
- Seleção por `STT_PROVIDER` (`auto` | `mlx` | `faster_whisper` | `openai`);
  `auto` resolve pela plataforma; escolha incompatível **falha no boot**
  (ADR-0027, item 3) — nunca fallback silencioso.
- `mlx-whisper` como extra opcional do `pyproject.toml`, importado dentro da
  construção do adapter (no topo do módulo quebraria a máquina x86 que não o
  tem).
- CPU-bound em código async: `run_in_executor` — o `faster-whisper` segura o
  GIL e travaria o event loop do worker.
- Esqueleto do adapter OpenAI atrás de `STT_PROVIDER=openai` (modo qualidade).

**`small.en` é o default e a escolha de modelo continua BLOQUEADA**
(ADR-0027, item 7). O `base.en` **não** é a alternativa rápida que parecia: ao
reexecutar, deu 0,78 s contra os 0,20 s da primeira medição, com custo quase
fixo de ~0,75 s (medição §3.3). E qualidade nunca foi medida — os 100% de
concordância da §3.4 vieram de áudio sintético de `tts-1`, o caso trivial.
Este card **não fecha** essa escolha; registra o gatilho (voz de aprendiz).

## Escopo

- **In:** porta, dois adapters locais, seleção por config, testes.
- **Out:** STT incremental/streaming (V2 — ADR-0003); WER e escolha de modelo
  (eval, Fase 4); carga residente (CARD-009, ADR-0025).

## Critérios de aceite

- **Dado** um wav conhecido, **quando** `transcribe` roda em cada adapter,
  **então** o texto contém as palavras-chave esperadas (integração, `slow`).
- **Dado** `STT_PROVIDER=mlx` numa máquina não-Apple-Silicon, **então** o boot
  falha com mensagem que nomeia a plataforma — testado, não presumido.
- **Dado** `STT_PROVIDER=auto`, **então** o adapter escolhido é determinado pela
  plataforma e **logado na subida** (a latência precisa ser explicável depois).
- **Dado** a porta, **quando** `application` é testada, **então** usa um fake em
  memória, sem tocar em nenhuma biblioteca de STT.
- Quality gates verdes com o override de `mypy` do `mlx-whisper` **pontual e
  comentado** com o gatilho de remoção.

## Riscos

Download do modelo no primeiro uso (36–99 s medidos, uma vez) — cachear e
documentar no README; a assimetria de CI (o caminho `mlx` não roda no CI) está
registrada no ADR-0027 e é aceita, não resolvida.

## Objetivo de aprendizado

`Protocol` na prática (o fake do teste não declara `implements` — só tem o
método certo; **e o momento em que se descobre que ele não satisfaz a porta** —
esta é a Q7 de `docs/perguntas-em-aberto.md`, que volta aqui) e
`run_in_executor` para CPU-bound em async: o paralelo de `Task.Run`, com a
diferença do GIL.
