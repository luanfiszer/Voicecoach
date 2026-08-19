# ADR-0027 — Adapter duplo de STT (`mlx-whisper` e `faster-whisper`), com o default resolvido pela plataforma

- **Status:** aceito
- **Data:** 2026-08-19
- **Complementa:** [ADR-0011](0011-stt-e-tts-locais-como-default.md) (que pedia
  esta avaliação por escrito), ADR-0013 (configuração tipada), ADR-0025
  (modelos residentes)
- **Consome:** [`medicao-latencia.md`](../medicao-latencia.md) §3.2, §3.3, §3.4
- **Critérios de obrigatoriedade:** **1 — introduz dependência externa**
  (`mlx-whisper` ao lado de `faster-whisper`) e **2 — define uma fronteira**
  (uma porta, duas implementações, com escolha de default).

## Contexto

O ADR-0011 escolheu `faster-whisper` como default e deixou escrito que
`mlx-whisper` deveria ser avaliado na implementação. A avaliação foi feita:

| Modelo | `faster-whisper` (CPU) | `mlx-whisper` (GPU Apple) | Ganho |
|---|---|---|---|
| `small.en`, 17,6 s de áudio | 1,18 s (`float32`) | **0,59 s** | **2,0×** |
| `small.en`, 17,6 s de áudio | 1,48 s (`int8`) | **0,59 s** | 2,5× |
| `small.en`, 62,5 s de áudio | 5,90 s | **2,06 s** | 2,9× |
| ~~`base.en`, 17,6 s~~ | ~~0,48 s~~ | ~~0,20 s~~ | **não confirmado** |

> **A linha do `base.en` caiu.** Ao reexecutar o benchmark como instrumento
> versionado, o `base.en` deu **0,78–0,79 s** — estável em três execuções, logo
> não é ruído — contra os 0,20 s da primeira medição, e com custo quase fixo de
> ~0,75 s que a duração do áudio não explica (medição §3.3). Ele deixa de ser
> uma opção mais rápida: no `mlx`, `base.en` é **mais lento** que `small.en`.
> **Só o `small.en` decide alguma coisa aqui.**

Dois achados que mudam o desenho, não só o número:

1. **`mlx-whisper` só roda em Apple Silicon.** Numa máquina x86 hospedada, o
   pacote não é opção — nem por configuração.
2. **Ele libera a CPU**, que no worker disputa com o TTS (ADR-0025). O ganho
   real é maior que a tabela sugere, e não foi medido sob contenção.

E um terceiro achado, que **bloqueia** parte da decisão: as 16 variantes deram
**100% de concordância** de transcrição, inclusive o modelo mais barato — porque
o áudio de teste era saída de `tts-1`, inglês nativo sintético, sem sotaque,
disfluência ou ruído. **Latência está medida; qualidade não** (medição §3.4).

## Decisão

**Uma porta `SpeechToText`, dois adapters locais, e o default resolvido pela
plataforma no boot — com a escolha do *modelo* explicitamente adiada.**

1. **`adapters/stt/mlx_whisper_adapter.py`** e
   **`adapters/stt/faster_whisper_adapter.py`** implementam a mesma porta. O
   adapter de API paga (ADR-0011) continua previsto e não muda.
2. **Seleção por configuração** (`STT_PROVIDER`, ADR-0013) com um valor a mais:
   `auto` (default). Em `auto`, o boot escolhe `mlx` se a plataforma for Apple
   Silicon e `faster_whisper` caso contrário.
3. **Escolha explícita incompatível é erro de boot, não fallback silencioso.**
   `STT_PROVIDER=mlx` numa máquina x86 **falha na subida com mensagem clara**.
   Cair de volta para o outro adapter esconderia uma regressão de 2,4× em
   latência atrás de um log — a mesma classe de falha silenciosa do ADR-0021 e
   do ADR-0022.
4. **`mlx-whisper` é dependência opcional** (extra do `pyproject.toml`,
   instalado no ambiente de dev Apple; ausente na imagem x86), e o adapter
   importa a biblioteca **dentro** da própria construção, não no topo do módulo
   — importar no topo quebraria a máquina que não a tem, mesmo sem usá-la.
5. **`float32` é o default de quantização, não `int8`.** Medido: `int8` é
   **mais lento** neste hardware (1,48 s → 1,18 s ao *abandonar* a quantização).
   Adotar `int8` "porque é mais leve" é otimização por hábito, e a medição já a
   desmentiu.
6. **`beam_size=1` como default** (corta ~30% contra `beam_size=5`), revisável
   quando houver medida de qualidade.
7. **`small.en` é o default, e a escolha de modelo continua BLOQUEADA** até
   existir insumo com **voz real de aprendiz**. O `small.en` é o único número
   que reproduziu; e mesmo que o `base.en` fosse rápido, a qualidade nunca foi
   medida — os 100% de concordância vieram de áudio sintético (medição §3.4).
   Sob incerteza de qualidade, erra-se para o lado que não estraga a
   transcrição. **Gatilho para reabrir:** regravar o insumo com voz de aprendiz
   e repetir a medição §3.2/§3.3.
8. **O VAD do `faster-whisper` segue não avaliado** — o insumo sintético não
   tinha silêncio nem hesitação para o VAD ter o que fazer. Default ligado,
   como no protótipo, e a avaliação vai junto com o item 7.

## Alternativas consideradas

### Alternativa A — Só `mlx-whisper`, e resolver o x86 quando hospedar

- **O que é:** adotar o mais rápido e adiar o problema.
- **Por que foi rejeitada:** transformaria "hospedar" numa tarefa de reescrever
  adapter sob pressão, e o CI (que roda em x86) não conseguiria exercitar o
  caminho de STT. A regra de camadas existe para que trocar provider seja
  configuração — não usá-la aqui seria desperdiçar a costura já paga.

### Alternativa B — Só `faster-whisper`, ignorando o ganho de 2,4×

- **O que é:** manter o ADR-0011 como está.
- **Por que foi rejeitada:** 0,59 s de diferença (1,18 → 0,59 s no `small.en`)
  é **um terço** do orçamento de 1,8 s, na máquina que é o ambiente de
  desenvolvimento e de demonstração do produto. Sob a regra de desempate
  ("cede escopo, nunca latência"), não se joga fora.

### Alternativa C — Escolher em runtime, por job, o adapter mais rápido disponível

- **O que é:** tentar `mlx`, cair para `faster_whisper` em erro.
- **Por que foi rejeitada:** é o fallback silencioso do item 3 promovido a
  arquitetura. Latência que varia sem que ninguém saiba por quê é o oposto do
  que um alvo medido exige.

## Consequências

**Positivas**

- 2× de STT na máquina onde o produto é desenvolvido e demonstrado, e CPU
  livre para o TTS no mesmo worker (ADR-0025).
- Cobra o investimento das portas do ADR-0003/0011 pela primeira vez com duas
  implementações **reais** — o teste de que a fronteira funciona deixa de ser
  hipotético.
- A escolha de modelo fica adiada **com gatilho escrito**, em vez de fixada por
  um dado que não a sustenta.

**Negativas — o preço aceito**

- **Dois adapters para manter e testar**, um deles inexecutável no CI. O caminho
  x86 é o que o CI cobre; o caminho Apple depende de teste local marcado `slow`
  — assimetria real de cobertura, registrada aqui para não virar surpresa.
- **Dependência opcional com import tardio** é um idioma que engana: `mypy` e
  `ruff` veem o módulo, a máquina de CI não tem o pacote. Precisa de override
  pontual e comentado (regra do `CLAUDE.md`).
- **Os números não transferem para máquina hospedada.** Todos foram medidos num
  M4; em x86 sem Neural Engine o adapter default muda e o orçamento de latência
  precisa ser **remedido antes** de qualquer promessa de produto rodando fora
  desta máquina.
- **A conta do ADR-0025 fica incompleta** enquanto a carga do `mlx-whisper` não
  for medida em separado.
