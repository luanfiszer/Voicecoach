# ADR-0029 — O que atravessa a porta de STT são bytes codificados, e a decodificação mora no adapter

- **Status:** aceito
- **Data:** 2026-08-19
- **Complementa:** [ADR-0027](0027-adapter-duplo-de-stt-com-default-resolvido-pela-plataforma.md)
  (que decidiu *quais* adapters existem, mas não o que trafega entre eles),
  [ADR-0012](0012-regra-de-camada-como-contrato-executavel.md), ADR-0003
- **Consome:** [`medicao-latencia.md`](../medicao-latencia.md) §3.5
- **Critérios de obrigatoriedade:** **2 — define uma fronteira** (o tipo que
  atravessa a porta `SpeechToText`, e de que lado dela mora a decodificação de
  áudio).

## Contexto

O ADR-0027 decidiu que existem dois adapters de STT para uma porta. Ele **não**
disse o que a porta recebe — e essa lacuna tem apenas três respostas possíveis,
com consequências muito diferentes.

Dois fatos, verificados no CARD-006 contra as bibliotecas instaladas e não
contra a documentação delas:

1. **`mlx_whisper.transcribe()` aceita `str | np.ndarray`.** Quando recebe uma
   `str`, ele chama `load_audio()`, que dispara o binário **`ffmpeg` via
   subprocesso** — *"Requires the ffmpeg CLI in PATH"*. A máquina de
   desenvolvimento **não tem `ffmpeg` no PATH** (`which ffmpeg` → nada). O
   benchmark do ADR-0027 nunca exercitou esse caminho porque já entregava um
   `ndarray` lido pelo `soundfile`.
2. **O `faster-whisper` traz o PyAV**, e expõe `decode_audio(BinaryIO)`, que lê
   AAC/Ogg/WAV **sem** binário externo.

E um número que faltava. Os benchmarks de STT tiram a decodificação de dentro da
medição de propósito; o adapter real não tem esse luxo, e o custo dela conta no
orçamento de 1,8 s. Medido (§3.5), num turno de ~20 s:

| Formato | Tamanho | Decodificação |
|---|---|---|
| WAV PCM16 | 596 KB | 5,0 ms |
| **AAC 64k** (o que o Expo grava) | 151 KB | **6,0 ms** |
| Ogg/Opus 24k | 52 KB | 24,0 ms |

**6 ms é 0,3% do orçamento e 1% do próprio STT.** A decodificação não é um
trade-off; é ruído.

## Decisão

**A porta `SpeechToText` trafega `AudioInput(data: bytes)` — o arquivo
codificado, como veio do storage — e devolve `Transcript(text, language,
duration_seconds)`. Decodificar é responsabilidade do adapter, numa única
implementação compartilhada pelos dois.**

1. **`AudioInput` carrega só `bytes`.** Sem `content_type`: o decodificador
   identifica o container lendo os próprios bytes, e um campo que ninguém usa é
   um campo que pode mentir quando o cliente mandar o rótulo errado.
2. **Nenhum tipo de biblioteca atravessa a porta.** `numpy` e `av` entram nas
   listas `forbidden` de `domain` e `application` no mesmo commit — `numpy` é o
   vazamento fácil de cometer sem querer, porque `NDArray[np.float32]` é o tipo
   *natural* para "áudio" e passaria despercebido numa revisão.
3. **`voicecoach/adapters/stt/audio.py` é a única implementação da
   decodificação**, sobre `faster_whisper.audio.decode_audio` (PyAV). Os dois
   adapters a usam. Se cada um decodificasse do seu jeito, comparar a latência
   dos dois compararia duas coisas diferentes.
4. **`Transcript.duration_seconds` é derivado das amostras**, não lido do que
   cada biblioteca reporta — o `faster-whisper` tem `info.duration` e o
   `mlx-whisper` não tem equivalente. Derivando, o campo significa exatamente a
   mesma coisa nos dois adapters, o que importa porque ele vira **cota do aluno**
   (`daily_audio_minutes_per_student`).
5. **Requisito para o cliente (CARD-011): gravar em AAC, não em Opus.** É o
   default do Expo nos dois SOs, e é a diferença entre 6 ms e 24 ms.

## Alternativas consideradas

### Alternativa A — A porta recebe um caminho de arquivo

- **O que é:** o worker baixa o objeto do storage para um temporário e passa o
  `Path`; cada biblioteca lê o arquivo como preferir.
- **Por que foi rejeitada:** é o caminho que **exige `ffmpeg` no PATH** para o
  `mlx-whisper` — dependência de sistema no Dockerfile e na máquina de
  desenvolvimento, que hoje não a tem. Paga ainda o *spawn* de um processo por
  turno (dezenas de ms, contra 6) e um arquivo temporário para dado que já está
  em memória. Perde em todos os eixos.

### Alternativa B — A porta recebe amostras já decodificadas (`ndarray`)

- **O que é:** empurrar a decodificação para o chamador; o adapter recebe PCM.
- **Por que foi rejeitada:** `numpy` viraria dependência de `application` — a
  camada que o ADR-0012 mantém livre de biblioteca. Pior: amarraria o contrato
  ao formato interno *atual* dos adapters, e o dia em que um provider remoto
  entrar (ADR-0011, modo qualidade) ele receberia amostras para reencodar antes
  de subir. É acoplamento com custo negativo.

### Alternativa C — O cliente manda PCM, e ninguém decodifica no servidor

- **O que é:** eliminar a etapa movendo-a para o app.
- **Por que foi rejeitada:** não elimina o custo, **move para a rede** — e para
  o lado caro. WAV são 596 KB contra 151 KB do AAC: ~445 KB a mais de upload,
  ~0,7 s em 4G. Trocar 6 ms de CPU por 700 ms de rede móvel é a pior troca
  possível num orçamento de 1,8 s, e a regra de desempate da reconstrução
  ("cede escopo, nunca latência") a proíbe.

## Consequências

**Positivas**

- A porta fica **pobre e estável**: bytes entram, texto sai. O V2 acrescenta
  `stream_transcribe` por extensão (ADR-0003) sem mexer nesta assinatura.
- O contrato do import-linter passa a **vigiar `numpy`**, que era o vazamento
  mais provável desta fronteira e não estava coberto por nada.
- `Transcript` já carrega a duração que a cota (CARD-015) vai precisar, sem
  decodificar o áudio uma segunda vez só para contar.
- A decodificação virou **instrumento versionado** (`benchmarks/stt_decode.py`)
  e insumo fixo em três formatos, em vez de suposição.

**Negativas — o preço aceito**

- **O caminho `mlx` passa a depender do `faster-whisper`** para decodificar.
  Não custa instalação nova (o `faster-whisper` é dependência base nas duas
  plataformas), mas é um acoplamento entre adapters que não existiria se
  escrevêssemos o laço de reamostragem à mão. Trocamos independência por ~50
  linhas de código nosso a manter e testar. **Gatilho para reavaliar:** o dia em
  que o `faster-whisper` deixar de ser dependência base.
- **O áudio inteiro fica em memória** como `bytes` e de novo como `ndarray`
  (~1,2 MB de PCM para 20 s). Irrelevante para um worker de uso pessoal, e um
  problema real se um dia houver concorrência alta. **Gatilho:** turnos maiores
  que 5 minutos ou mais de ~20 jobs simultâneos por processo.
- **A decodificação não está no orçamento medido ponta a ponta**, porque esse
  orçamento ainda não existe (CARD-012). Os 6 ms são de componente isolado, com
  os bytes já em memória — **o download do storage é outra linha, maior, e não
  foi medida**.
