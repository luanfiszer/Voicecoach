# CARD-006 — Porta SpeechToText + adapters `mlx-whisper` e `faster-whisper`

- **ID:** CARD-006 · **Épico:** Fase 1 — Fatia vertical em cascata
- **Plataforma:** backend/IA · **Esforço:** M · **Status:** **concluído** (2026-08-19)
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


---

## Execução (2026-08-19)

Branch `card-006-porta-e-adapter-stt-local`, a partir de `main` (o CARD-018 já
estava mergeado pelo PR #10).

### O que foi entregue

| Arquivo | O que é |
|---|---|
| `application/ports/speech_to_text.py` | porta `SpeechToText` (`Protocol`) + `AudioInput` + `Transcript` |
| `adapters/stt/audio.py` | decodificação compartilhada: bytes → PCM 16 kHz mono, via PyAV |
| `adapters/stt/faster_whisper_adapter.py` | adapter de CPU, com os parâmetros medidos e `run_in_executor` |
| `adapters/stt/mlx_whisper_adapter.py` | adapter de GPU Apple, com o import tardio |
| `adapters/stt/factory.py` | resolução por plataforma no boot, falha explícita e log |
| `config.py` | `SttProvider` (StrEnum) + `stt_provider` + as duas strings de modelo |
| `benchmarks/stt_decode.py`, `make_inputs.py` | instrumento e insumo novos (AAC/Opus) |
| `tests/fixtures/stt/amazing-project.wav` | 72 KB, 2,3 s, versionado com exceção no `.gitignore` |
| `docs/adr/0029-…` | o que atravessa a porta, e de que lado a decodificação mora |

**Descoberta que mudou o desenho, e que o card não previa.** O
`mlx_whisper.transcribe()` só aceita caminho de arquivo delegando ao binário
`ffmpeg` no PATH — e `which ffmpeg` não devolve nada nesta máquina. O benchmark
do ADR-0027 nunca exercitou esse caminho porque já entregava um `ndarray`.
Isso eliminou "caminho de arquivo" como tipo da porta e gerou o ADR-0029.

### Critérios de aceite, um a um

**1. Dado um wav conhecido, `transcribe` devolve o texto esperado nos dois adapters.**

```
$ uv run pytest -m slow -q
...                                                                      [100%]
3 passed, 3 deselected in 25.86s
```

Insumo versionado (`amazing-project.wav`, 2,3 s), asserção por palavra-chave
(`amazing`, `project`) e não por igualdade — exigir a string exata
transformaria diferença de pontuação entre modelos em falha de teste.

**2. `STT_PROVIDER=mlx` em plataforma incompatível falha no boot nomeando a
plataforma — testado, não presumido.**

```
$ STT_PROVIDER=mlx uv run python -c "... platform.machine = lambda: 'x86_64' ..."
STT_PROVIDER lido da env = mlx
voicecoach.adapters.stt.factory.SttProviderUnavailableError: STT_PROVIDER=mlx
exige Apple Silicon, mas esta máquina é darwin/x86_64. O mlx-whisper não roda
aqui. Use STT_PROVIDER=faster_whisper, ou 'auto' para resolver pela plataforma.
```

**3. `STT_PROVIDER=auto` resolve pela plataforma e é logado na subida.**

```
INFO voicecoach.adapters.stt.factory: STT: STT_PROVIDER=auto resolvido para 'mlx' (plataforma darwin/arm64)
INFO voicecoach.adapters.stt.factory: STT: carregando modelo mlx 'mlx-community/whisper-small.en-mlx'
adapter construído: MlxWhisperSpeechToText
```

**4. O teste de `application` usa fake em memória, sem tocar biblioteca de STT.**
`tests/application/test_speech_to_text_port.py` — o fake não declara herança
nenhuma; quem confere a conformidade é o `mypy`, na linha
`stt: SpeechToText = FakeSpeechToText(...)`.

**5. Quality gates verdes com o override de `mypy` pontual e comentado.**
Override por módulo (`faster_whisper.*`, `mlx_whisper.*`), cada um com o motivo
e o **gatilho de remoção** escrito. O `strict` global não foi tocado.

### Gates (todos verdes, de `backend/`)

```
$ uv run ruff format --check src tests   → 41 files already formatted
$ uv run ruff check src tests            → All checks passed!
$ uv run mypy                            → Success: no issues found in 41 source files
$ uv run lint-imports                    → Contracts: 4 kept, 0 broken.
$ uv run pytest --cov --cov-fail-under=80 → 80 passed, 3 deselected
                                            Total coverage: 91.85%
$ uv run coverage report --include="*/domain/*,*/application/*" --fail-under=90
                                          → TOTAL 164 0 24 0 100%
```

Cobertura: núcleo **100%**, global **91,85%** (era 91,0% no fim do CARD-018 —
não caiu). O que fica descoberto no run padrão são as duas funções de carga de
modelo, exercitadas só pelos testes `slow`.

**Prova de que os contratos mordem** (injetada e revertida). Duas violações
dentro de `application/ports/speech_to_text.py`:

| Violação | Veredito |
|---|---|
| `from faster_whisper import WhisperModel`, com o módulo **fora** da lista | `4 kept, 0 broken` — passou verde |
| a mesma linha, com `faster_whisper` **na** lista | `application is not allowed to import faster_whisper (l.5)` |
| `from voicecoach.adapters.stt... import ...` | quebra o contrato de **layers**, sem lista nenhuma |
| `transcribe(audio: NDArray[np.float32])` na porta | `application is not allowed to import numpy (l.33, l.34)` |

### Item de ADR da DoD (critério escrito, LEARNING-0003)

Consultada a lista "Quando um ADR é OBRIGATÓRIO" de `docs/adr/README.md`:

- **Critério 1 (dependência externa)** e **critério 2 (fronteira)** aplicados ao
  par de adapters: **já cobertos pelo ADR-0027**, que este card implementa. Sem
  ADR novo por eles.
- **Critério 2 dispara de novo**, e por decisão que o ADR-0027 não cobria: *o
  que atravessa a porta* e *de que lado mora a decodificação*. Escrito o
  **ADR-0029**, com as três alternativas reais (caminho de arquivo, `ndarray`,
  PCM enviado pelo cliente) e o motivo medido de cada rejeição.
- **Critério 4 (privacidade)** conferido para o insumo versionado: o clipe é
  saída de `tts-1` sintético, **não é voz de pessoa real** — não dispara.

### Regra do explicador — desfecho

| # | Pergunta | Momento | Desfecho |
|---|---|---|---|
| **Q3** | Contrato de dependência vs. de direção: em que cenário só o segundo pega a violação? | antes de escrever as listas `forbidden` | **respondida** (na reformulação). Primeira resposta parcialmente errada ("A quebra o forbidden" — A passou verde, porque o módulo ainda não estava na lista); reformulada uma vez e respondida corretamente: só o `layers` quebra, e nenhuma lista o torna redundante |
| **Q7** | O que `Protocol` faz que dispensa mock, e quando se descobre que um fake não satisfaz a porta? | antes de escrever o fake | **dispensada pelo desenvolvedor** ("vamos pular essas perguntas e finalizar a implementação"). **Permanece na fila** de `docs/perguntas-em-aberto.md` |

Nota: a demonstração da Q7 aconteceu por acidente durante a implementação — um
fake com o primeiro parâmetro renomeado passou no `pytest` (6 passed) e foi
reprovado pelo `mypy` (`incompatible type ... expected "_TranscribeFn"`).
Registrado como evidência do mecanismo, **não** como fechamento do item: item
fechado pelo agente com a própria explicação não conta (LEARNING-0004).

### Achados fora do escopo, corrigidos

1. **`alembic/env.py` desativava todos os loggers do processo.** O template do
   Alembic chama `fileConfig()` com o default `disable_existing_loggers=True`.
   Como os testes de adapter rodam migration em processo (ADR-0018), o logger da
   fábrica de STT era silenciado — o teste do critério 3 passava sozinho e
   falhava na suíte. Corrigido para `disable_existing_loggers=False`.
2. **Os insumos de `benchmarks/inputs/` mudaram** desde a sessão de medição:
   `curto.wav` é 19,08 s (`b2e8fe4e…`) e não os 17,57 s (`b8dc14b0…`) de
   `medicao-latencia.md` §2. As tabelas §3.2/§3.3 **não reproduzem byte a byte**
   hoje. Ressalva registrada na §3.5.

### Dívidas explícitas

| Dívida | Quem resolve |
|---|---|
| **Sem consumidor.** Não existe worker nem caso de uso; a fábrica é exercitada por teste, não por um processo subindo | CARD-009 (ADR-0025, carga residente) |
| **Adapter OpenAI cortado.** `SttProvider.OPENAI` existe no enum e a fábrica levanta `NotImplementedError` nomeando o motivo — o ADR-0010 restringe gasto ao Claude, então o adapter nunca poderia ser exercitado | card próprio, se o modo qualidade for reaberto |
| **`uv sync --extra mlx` puxa `torch`** (~1,3 GB de `.venv`). O ADR-0027 não previa; o CI não paga, porque sincroniza sem o extra | aceito; documentado no `backend/README.md` |
| **O caminho `mlx` não roda no CI** (x86) | assimetria aceita no ADR-0027; não se resolve sem runner ARM |
| **Escolha de modelo continua BLOQUEADA** e o VAD segue não avaliado | ADR-0027 itens 7 e 8 — gatilho é regravar o insumo com voz de aprendiz |
| **Download do storage não medido**; os 6 ms de decodificação pressupõem bytes em memória | CARD-009 / CARD-012 |
