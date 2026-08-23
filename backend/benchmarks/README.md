# Benchmarks

Instrumentos da sessão de medição de 2026-08-19. Os resultados e a leitura deles
estão em [`docs/medicao-latencia.md`](../../docs/medicao-latencia.md); aqui está
só como reproduzir.

Eles existem porque **benchmark que não se reexecuta vira folclore em três
meses**. Em particular, dois números do projeto dependem de rodá-los de novo:

- a escolha de modelo do STT, hoje **bloqueada** por falta de áudio de aprendiz;
- o veredito de latência **numa máquina hospedada**, que os números atuais
  (Apple M4) não cobrem.

## Por que não estão sob `uv run`

As dependências estão em `requirements.txt`, **fora do `pyproject.toml`**. Elas
somam alguns GB (torch, mlx, spacy, transformers) e são instrumento, não
produto — no `pyproject` fariam todo `uv sync`, inclusive o do CI, baixá-las
para rodar testes que não as usam.

```bash
cd backend/benchmarks
uv venv --python 3.12
uv pip install --python .venv -r requirements.txt
```

> **Exceção: `llm_primeira_sentenca.py` roda no venv do PROJETO, não neste.**
> Ele mede o adapter de produção (`AnthropicTeacher`), então precisa do
> `voicecoach` importável — e o `anthropic` e o `jiter` já são dependências do
> produto desde o CARD-007. Rode-o com `uv run python llm_primeira_sentenca.py`
> a partir desta pasta, com `ANTHROPIC_API_KEY` no ambiente.
>
> **`llm_streaming_spike.py` e `llm_primeira_sentenca.py` GASTAM DINHEIRO**
> (~US$ 0,03 e ~US$ 0,02 por execução, `claude-haiku-4-5`). Ambos imprimem o
> custo real da execução a partir do `usage` de cada chamada, e ambos hasheiam o
> insumo — se o prompt mudar, o hash muda e as tabelas da medição deixam de
> valer explicitamente.

`mypy` e `import-linter` não alcançam esta pasta (o alvo deles é `src tests`).
`ruff format` e `ruff check` **alcançam** — estes scripts passam nos mesmos
gates que o resto do backend.

### Ouvir o TTS (`tts_audicao.py`)

O único eixo do desempate Kokoro vs Piper que não é automatizável é a **qualidade
percebida** — a §9.4 da medição diz isso, e o ADR-0032 a registra como dívida
aberta. Este script é o instrumento dela:

```bash
cd backend
uv run python benchmarks/tts_audicao.py                     # correção pedagógica padrão
uv run python benchmarks/tts_audicao.py "o texto que quiser"
```

Ele roda no venv do **projeto** (como o `llm_primeira_sentenca.py`), porque
exercita o adapter de produção: o que você ouve é o que o aluno ouviria. Toca
cada voz de `voices/` em sequência e deixa os WAVs em `/tmp`.

### Vozes do Piper (CARD-008)

O Piper **não embarca vozes**: cada uma é um par `.onnx` (60 MB) + `.onnx.json`,
o análogo dos pesos do Whisper. Baixe antes de rodar `tts_piper.py`:

```bash
.venv/bin/python -m piper.download_voices \
  en_US-lessac-medium en_US-amy-medium --download-dir voices
```

`voices/` está no `.gitignore` — é artefato, não código. Em compensação, o Piper
**não tem dependência de sistema**: ele embarca o `espeak-ng-data` dentro do
wheel e fonemiza numa extensão compilada. A seção abaixo, que descreve três
consertos de ambiente, vale **só para o Kokoro** — e é o que a §9 da medição
mede como diferença de empacotamento.

### Dependência de sistema: `espeak-ng` (só para o Kokoro)

O Kokoro **não roda out-of-the-box**. Três armadilhas, todas encontradas na
sessão e todas relevantes para o Dockerfile do CARD-008:

1. o binário que vem no wheel do `espeakng-loader` tem o caminho de dados da
   máquina de CI compilado dentro, e falha com
   `'/Users/runner/.../phontab': No such file or directory`;
2. o conserto é apontar o `EspeakWrapper` para um `espeak-ng` de sistema
   **depois** do `import kokoro` — a `misaki` reatribui a biblioteca no import
   dela, sobrescrevendo o que se configure antes;
3. o Kokoro puxa spaCy e exige o modelo `en_core_web_sm`, não declarado.

```bash
brew install espeak-ng          # ou o pacote equivalente da distribuição
uv pip install --python .venv \
  https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl
```

Em Linux, aponte `ESPEAK_LIB` e `ESPEAK_DATA` para os caminhos da distribuição.

## O insumo de áudio NÃO está no repositório

`english_teacher_bot/temp_audio/` está no `.gitignore`, e `*.wav` também. **De um
clone limpo não é possível reproduzir os números exatos** — só o método.

```bash
.venv/bin/python make_inputs.py <pasta-com-audio>
```

Isso grava, para cada duração alvo, **três arquivos com o mesmo PCM por trás** —
e imprime o SHA-256 de cada um:

| Arquivo | Para que serve |
|---|---|
| `curto.wav`, `longo.wav` | insumo dos benchmarks de STT: decodificação fora da medição |
| `curto.m4a`, `longo.m4a` | AAC 64 kbps — o que o Expo grava por padrão no iOS e no Android, ou seja, o que o adapter vai **de fato** receber |
| `curto.opus`, `longo.opus` | Ogg/Opus 24 kbps — o formato do protótipo de WhatsApp, mantido porque é a única variante cuja decodificação aparece no orçamento |

**Anote os hashes**: números só se comparam entre si quando o insumo é
byte-idêntico. Isso não é retórica — os arquivos foram regerados entre a sessão
de medição e o CARD-006, e as tabelas §3.2/§3.3 de `medicao-latencia.md` **não**
reproduzem byte a byte hoje (ressalva registrada na §3.5 daquele documento).

> A codificação usa **PyAV**, não o binário `ffmpeg`: a máquina de
> desenvolvimento não o tem no PATH. Isso não é detalhe de conveniência — é a
> mesma armadilha que o adapter de STT evita, porque
> `mlx_whisper.transcribe()` exige `ffmpeg` no PATH quando recebe um caminho de
> arquivo (ADR-0029).

> ⚠️ O insumo usado em 2026-08-19 foi saída de TTS sintético — inglês nativo,
> sem sotaque, sem hesitação. É o **caso trivial** do Whisper, e por isso as 16
> variantes deram 100% de concordância. Esses arquivos medem latência
> honestamente e **não medem qualidade**. Para decidir modelo é preciso áudio de
> aprendiz brasileiro real.

## Os scripts

| Script | O que mede | Custa dinheiro? |
|---|---|---|
| `make_inputs.py` | — (constrói os insumos, nos três formatos) | não |
| `stt_faster_whisper.py` | carga do modelo e transcrição: modelo × `beam_size` × VAD × quantização | não |
| `stt_mlx.py` | o mesmo com `mlx-whisper` — **só Apple Silicon** | não |
| `stt_decode.py` | decodificação do áudio comprimido em PCM — a etapa que os dois de cima tiram de fora de propósito | não |
| `tts_kokoro.py` | carga do pipeline e síntese: resposta inteira vs. uma frase | não |
| `llm_haiku.py` | tempo até o primeiro token vs. até o JSON completo | **~US$ 0,05** |
| `llm_cache_threshold.py` | prefixo mínimo cacheável, e o custo de um prefixo volátil | **~US$ 0,10** |

Os dois últimos exigem `ANTHROPIC_API_KEY` no ambiente e respeitam
`TEACHER_MODEL` (default `claude-haiku-4-5`, conforme ADR-0010).

Resultados vão para `results/*.json` (ignorado pelo git).

## O protocolo, que é o que dá valor aos números

Está em `_common.py` e vale para todos:

- **insumo fixo**, com hash conhecido;
- **primeira execução descartada** — ela carrega caches e aquece o modelo, e não
  é latência de turno;
- **p50 e p95 por posição**, nunca média. Com n=5, interpolar percentil é falsa
  precisão: o p95 de cinco amostras é o maior valor, e é honesto dizer isso;
- **modelo carregado uma vez por configuração**, reaproveitado entre repetições
  — é o cenário "residente no worker";
- **carga do modelo medida à parte**, porque responde outra pergunta.

## O que estes benchmarks NÃO cobrem

Componentes isolados. **Somar as tabelas não dá a latência de um turn.** Fica de
fora: serialização e cópia de áudio entre etapas, contenção de CPU entre STT e
TTS, GIL, pickup da fila, upload do cliente e latência de descoberta. Esse número
só existe depois do worker (CARD-009), e o CARD-012 já o exige.
