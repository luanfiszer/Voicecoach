# Medição de latência e custo dos componentes de IA

- **Data:** 2026-08-19; §8 acrescentada em 2026-08-21 (CARD-007); §9 em
  2026-08-23 (CARD-008)
- **Status:** **completa** para os três componentes (STT, LLM, TTS)
- **Origem:** sessão de medição anterior aos adapters de IA (CARDs 006/007/008)

> Este documento existe para que os números citados em
> [`analise-custo-e-precificacao.md`](analise-custo-e-precificacao.md) e nos ADRs
> sejam verificáveis. Número sem método declarado é anedota.

---

## 1. O que esta medição NÃO cobre

Dizer isto primeiro, porque é o erro mais fácil de cometer com estas tabelas.

**Não existe pipeline para medir ponta a ponta.** Os adapters de STT (CARD-006),
LLM (007), TTS (008) e o worker (009) **não foram escritos**. O que está medido
aqui são **componentes isolados com insumo fixo**.

Somar as linhas **não** dá a latência de um turn. Fica de fora: serialização e
cópia do áudio entre etapas; contenção de CPU entre STT e TTS no mesmo worker e o
GIL; tempo de pickup da fila (arq/Redis); upload do cliente; latência de
descoberta do polling. Esse número só existe depois do CARD-009, e o **CARD-012
já o exige**.

## 2. Método

- **Insumo fixo de áudio**, WAV 16 kHz mono, derivado de
  `english_teacher_bot/temp_audio/`:

  | Arquivo | Duração | SHA-256 |
  |---|---|---|
  | `curto.wav` | 17,57 s | `b8dc14b0…c2c0c1ac` |
  | `longo.wav` | 62,54 s | `c0d9289e…b088a5df` |

- **Insumo fixo de texto** (TTS): resposta de 276 caracteres no formato que o
  prompt do professor pede (3–5 frases), e uma frase isolada de 61 caracteres.
- **Insumo fixo de prompt** (LLM): o `SYSTEM_PROMPT` real de
  `english_teacher_bot/teacher.py`, com histórico de 6 trocas.
- Língua forçada `en` no STT (preserva a decisão do protótipo — CARD-006).
- **1 execução de aquecimento descartada** por configuração.
- n = 5 (curto) / n = 3 (longo). Reporta-se **p50 e p95**, nunca média.
- Modelo carregado **uma vez por configuração** — cenário "residente no worker".
- **RTF** = tempo de processamento ÷ duração do áudio. Menor é melhor.
- **Máquina:** Apple M4, 16 GB RAM, macOS 26.5.1, 10 núcleos, sem outra carga
  pesada. **O número só vale nesta máquina** (ver §7).

---

## 3. STT

### 3.1 Tempo de carga do modelo

| Modelo | Carga **fria** (inclui download) | Carga com modelo em disco |
|---|---|---|
| `small` / int8 | 94,0 s | **0,42 s** |
| `small.en` / int8 | 99,0 s | **0,41 s** |
| `base.en` / int8 | 36,7 s | **0,24 s** |
| `small.en` / float32 | — | **0,46 s** |

### 3.2 `faster-whisper` (CPU, CTranslate2) — `curto.wav`, 17,57 s

| Modelo | Quant. | `beam_size` | VAD | p50 | p95 | RTF |
|---|---|---|---|---|---|---|
| `small` | int8 | 5 | on | 1,91 s | 1,96 s | 0,108 |
| `small` | int8 | 1 | on | 1,44 s | 1,47 s | 0,082 |
| `small.en` | int8 | 5 | on | 2,09 s | 2,15 s | 0,119 |
| `small.en` | int8 | 1 | on | 1,48 s | 1,50 s | 0,084 |
| `small.en` | **float32** | 1 | on | **1,18 s** | 1,22 s | 0,067 |
| `base.en` | int8 | 5 | on | 0,74 s | 0,76 s | 0,042 |
| `base.en` | int8 | 1 | on | **0,48 s** | 0,52 s | 0,028 |

`longo.wav` (62,54 s): `small.en` beam5 = 9,06 s · `small.en` beam1 = 5,90 s ·
`base.en` beam1 = 2,11 s.

- **`beam_size` 1 em vez de 5 corta ~30%** no curto e ~35% no longo.
- **O VAD não fez diferença** neste insumo — e não podia: é áudio de TTS, sem
  silêncio nem hesitação. **Segue não avaliado** para o caso real.
- **`int8` é mais LENTO que `float32` neste hardware** (1,48 → 1,18 s). A
  quantização otimiza para hardware que não é este. O CARD-006 não deve adotar
  `int8` por hábito.

### 3.3 `mlx-whisper` (GPU do Apple Silicon)

Avaliação que o [ADR-0011](adr/0011-stt-e-tts-locais-como-default.md) pedia por
escrito e nunca tinha sido feita.

| Modelo | `curto.wav` | `longo.wav` | RTF |
|---|---|---|---|
| `whisper-small.en-mlx` | **0,53 s** | **2,06 s** | 0,030 |
| `whisper-base.en-mlx` | **0,20 s** | **0,79 s** | 0,011 |

> ⚠️ **Correção de 2026-08-19, ao transformar os scripts em instrumento
> reexecutável.** Ao rodar `benchmarks/stt_mlx.py` três vezes com insumo novo, o
> `base.en` deu **0,78–0,79 s** no curto (RTF ~0,041), não os 0,20 s da primeira
> medição — e o número é **estável nas três execuções**, logo não é ruído. O
> `base.en` tem um custo quase fixo de ~0,75 s (0,78 s para 19 s de áudio,
> 0,85 s para 64 s), que a duração não explica. **A linha do `base.en` acima
> não está confirmada e não deve ser usada para decidir nada.** O `small.en`
> reproduziu (0,53 → 0,59 s) e é o número em que se pode confiar.

No `small.en` — o número confirmado — é **~2,5× mais rápido** que o `faster-whisper`, e libera a CPU —
que num worker disputaria com o TTS. **Apple Silicon apenas:** numa máquina x86
hospedada não roda. Não é trocar o default, é ter **dois adapters** — ADR novo.

### 3.4 Qualidade: por que esta coluna não decide nada

As 16 variantes deram **100% de concordância** com a referência (`small.en`
beam 5), inclusive `base.en` beam 1 — o mais barato e rápido da tabela.

Isso **não** significa que os modelos são equivalentes: significa que **o insumo
é trivial demais para discriminar**. Os arquivos são saídas do OpenAI `tts-1` —
inglês nativo sintético, sem sotaque, disfluência, pausa ou ruído.

> **A escolha de modelo do CARD-006 NÃO pode ser feita com estes dados.** Eles
> decidem latência; não decidem qualidade. **Gatilho:** regravar com voz real de
> aprendiz e repetir §3.2/§3.3 antes de fixar o modelo.

### 3.5 Decodificação do áudio — a etapa que as tabelas acima escondem

- **Medido em:** 2026-08-19, no CARD-006 · **Instrumento:** `benchmarks/stt_decode.py`

As tabelas §3.2 e §3.3 leem o WAV com `soundfile` **fora** da medição. Isso é
correto para a pergunta delas (quanto custa transcrever) e **enganoso** para o
orçamento: o adapter recebe do storage os bytes que o celular gravou — AAC ou
Opus, não PCM — e alguém paga a decodificação.

Insumo: os mesmos `curto`/`longo`, gravados agora também em AAC 64 kbps (o que
o Expo grava por padrão nos dois SOs) e Ogg/Opus 24 kbps (o formato do protótipo
de WhatsApp), todos derivados do mesmo PCM. n = 11, primeira execução
descartada, bytes já em memória.

| Insumo | Formato | Tamanho | p50 | % de 1,8 s |
|---|---|---|---|---|
| `curto` (19,1 s) | WAV PCM16 | 596 KB | 5,0 ms | 0,28% |
| `curto` (19,1 s) | **AAC 64k** | 151 KB | **6,0 ms** | **0,33%** |
| `curto` (19,1 s) | Opus 24k | 52 KB | 24,0 ms | 1,33% |
| `longo` (63,7 s) | WAV PCM16 | 1.992 KB | 7,0 ms | 0,39% |
| `longo` (63,7 s) | AAC 64k | 502 KB | 14,0 ms | 0,78% |
| `longo` (63,7 s) | Opus 24k | 175 KB | 73,0 ms | 4,06% |

**Leitura.** No caso real — turno de ~20 s em AAC — a decodificação custa
**6 ms, 0,3% do orçamento e 1% do próprio STT**. É ruído, e por isso a decisão
de decodificar **dentro do adapter** (ADR-0029) não precisa de contrapartida.

Três coisas que o número mostra e que a intuição erra:

1. **O formato importa 5 vezes, e quem o escolhe é o cliente.** Opus é o único
   que chega a aparecer. Isso vira requisito de captura para o CARD-011: gravar
   em AAC, não em Opus.
2. **Decodificar no servidor é a opção barata, não a cara.** A alternativa
   "cliente manda PCM" não elimina o custo, move ele para a rede: 596 KB contra
   151 KB são ~445 KB a mais de upload, ~0,7 s em 4G. Trocar 6 ms de CPU por
   700 ms de rede seria a pior troca possível neste orçamento.
3. **`ffmpeg` como subprocesso perde nos dois eixos** — paga o *spawn* do
   processo e vira dependência de sistema. É o caminho que
   `mlx_whisper.transcribe()` toma sozinho quando recebe um caminho de arquivo,
   e a razão pela qual a porta trafega bytes (ADR-0029).

> **Ressalva de insumo.** Os arquivos em `benchmarks/inputs/` **mudaram** desde
> a medição de §3.2/§3.3: hoje são `curto.wav` 19,08 s (`b2e8fe4e…`) e
> `longo.wav` 63,74 s (`5e73aeb4…`), contra os 17,57 s (`b8dc14b0…`) e 62,54 s
> (`c0d9289e…`) registrados em §2. As tabelas de STT **não reproduzem byte a
> byte** hoje. As razões entre configurações continuam válidas; os valores
> absolutos, remeça antes de citar.

> **Fora do escopo desta medição:** baixar o objeto do storage. Os tempos acima
> pressupõem os bytes já em memória, e o download é uma linha maior e separada
> (CARD-009).

---

## 4. TTS — Kokoro

### 4.1 Carga

| Etapa | Tempo |
|---|---|
| `import` do módulo | 1,91 s |
| Construção do `KPipeline` | 3,72 s |
| **Total até poder sintetizar** | **5,63 s** |

### 4.2 Síntese

| Texto | Caracteres | Áudio gerado | p50 | p95 | RTF |
|---|---|---|---|---|---|
| Resposta típica (3–5 frases) | 276 | 17,05 s | **1,68 s** | 1,68 s | 0,098 |
| Uma frase | 61 | 3,98 s | **0,41 s** | 0,41 s | 0,102 |

O RTF é praticamente constante (~0,10): o custo é **linear no tamanho do texto**,
sem penalidade fixa relevante.

### 4.3 Três dependências escondidas — achado de empacotamento para o CARD-008

O Kokoro **não roda out-of-the-box**. Foram necessários três consertos:

1. O pacote `espeakng-loader` publica um `.dylib` com o caminho de dados da
   máquina de CI compilado dentro — quebra em
   `'/Users/runner/work/.../phontab': No such file or directory`. Nem
   `ESPEAK_DATA_PATH` nem `EspeakWrapper.set_data_path()` **antes** do import
   resolvem.
2. O conserto é apontar `EspeakWrapper` para um `espeak-ng` de sistema
   (`brew install espeak-ng`) **depois** do `import kokoro` — a `misaki`
   reatribui a biblioteca no próprio import dela.
3. O Kokoro puxa **spaCy** e exige o modelo `en_core_web_sm`, que não vem como
   dependência declarada.

Isso é **dependência de sistema não-Python num container** — vai para o
Dockerfile, não para o `pyproject.toml`. É risco de CARD-008 que não estava
mapeado, e é argumento a favor de avaliar o **Piper** (que embarca os próprios
dados de espeak) antes de fixar o Kokoro.

---

## 5. LLM — `claude-haiku-4-5` com o prompt real do professor

### 5.1 Latência

| Caso | Entrada | Saída | **TTFT p50** | **Total p50** | Total p95 |
|---|---|---|---|---|---|
| Fala curta (42 chars) | ~1.100 tok | 145 tok | **0,73 s** | **1,86 s** | 2,42 s |
| Fala longa (280 chars) | ~1.100 tok | 388 tok | **0,60 s** | **3,48 s** | 3,59 s |

- **O TTFT é praticamente constante** (~0,6–0,7 s) e independe do tamanho da
  resposta. O que varia é o tempo de *geração*.
- **A diferença TTFT → total é de 1,1 s (curta) a 2,9 s (longa)** — é exatamente
  o que uma resposta em streaming economizaria, e o que a cascata TTS por sentença
  poderia aproveitar.
- **A saída dobra com a fala longa** (145 → 388 tokens): o custo por turn não é
  constante, varia ~2,7× com o quanto o aluno falou.

### 5.2 Prompt caching — o limiar mede 4.096 tokens, não 1.024

O [ADR-0020](adr/0020-prompt-caching-no-adapter-do-professor.md) foi escrito
assumindo prefixo mínimo cacheável de ~1.024 tokens. **Medido, é 4× isso.**

Bisseção com `cache_control` no bloco de `system`:

| Prefixo | Cache engatou? |
|---|---|
| 1.967 / 2.467 / 2.967 / 3.217 / 3.467 / 3.717 / **3.967** tok | **não** |
| **4.217** / 4.967 / 5.467 / 5.967 / 6.467 / 7.467 tok | **sim** |

**Limiar: 4.096 tokens** (entre 3.967 e 4.217 — a potência de dois óbvia).

**Consequência para este produto:** o `SYSTEM_PROMPT` tem ~700 tokens e cada
troca do histórico ~150. Seriam necessárias **~22 trocas** numa mesma conversa
para o prefixo cruzar 4.096. Uma sessão típica de 10–15 turns **nunca chega lá**.

> **O prompt caching, como o ADR-0020 o desenhou, não engata no uso real deste
> produto.** Confirmado empiricamente: nas 4 chamadas com o prompt real
> (1.084 tokens de entrada), `cache_creation` e `cache_read` foram **0** em todas.

### 5.3 O que acontece acima do limiar — e o custo de errar

Com prefixo de 4.861 tokens, comparando prefixo estável e prefixo com um
timestamp na primeira linha:

| Cenário | Escrita | Leitura | US$ de entrada |
|---|---|---|---|
| Estável — chamada 1 | 4.861 | 0 | 0,006082 |
| Estável — chamada 2 | 0 | 4.861 | **0,000492** |
| Estável — chamada 3 | 0 | 4.861 | **0,000492** |
| Timestamp — chamada 1 | 4.874 | 0 | 0,006098 |
| Timestamp — chamada 2 | 4.874 | 0 | **0,006098** |
| Timestamp — chamada 3 | 4.874 | 0 | **0,006098** |

- Com prefixo estável, a entrada fica **92% mais barata** a partir da 2ª chamada.
- Com prefixo volátil, **paga-se a escrita de cache toda vez e nunca se lê**. E
  como escrita custa **1,25×**, o resultado é **~25% mais caro que não usar
  cache nenhum**. Errar não é perder o desconto — é pagar multa.
- **Como se descobre:** `cache_read_input_tokens` permanece em 0. Nada falha,
  nenhuma resposta muda, nenhum erro é levantado. Só a fatura sobe.

---

## 6. Veredito sobre o orçamento de latência

A visão §D promete **texto em ≤ ~6 s** e **áudio completo em ≤ ~12–15 s p50**.
Somando as peças medidas para uma fala de ~17 s (caso base):

| Caminho | STT | LLM | TTS | **Total** | Orçamento | Veredito |
|---|---|---|---|---|---|---|
| Melhor (`mlx base.en`, fala curta) | 0,20 s | 1,86 s | — | **2,06 s** | ≤6 s texto | **folga de 3×** |
| Pior (`faster-whisper small.en`, fala longa) | 1,48 s | 3,48 s | — | **4,96 s** | ≤6 s texto | cabe |
| Melhor, com áudio | 0,20 s | 1,86 s | 1,68 s | **3,74 s** | ≤12–15 s | **folga de 3–4×** |
| Pior, com áudio | 1,48 s | 3,48 s | 1,68 s | **6,64 s** | ≤12–15 s | **folga de ~2×** |

**O orçamento é FOLGADO, não otimista.** Mesmo no pior caso medido, o áudio fica
pronto em ~6,6 s contra um teto de 12–15 s — e sobram ~6 s para o custo de
composição que a §1 lista (fila, storage, upload, polling).

Isto precisa ser dito com todas as letras porque a sessão nasceu de um incômodo
com a latência: **os números não sustentam que o alvo seja otimista.** O que
sobra é o que o [ADR-0003](adr/0003-interacao-v1-turn-based-preparada-para-v2-realtime.md)
já tinha nomeado e aceitado — o desconforto é com o **desenho turn-based em si**
(falar, parar, esperar, ouvir), não com o tempo de nenhuma etapa. Isso é o V2, e
o gatilho dele continua escrito.

### Consequência: duas alavancas mudam de status

| Alavanca | Antes | Depois da medição |
|---|---|---|
| **Cascata LLM→TTS por sentença** | "a maior de todas" | **desnecessária.** Economizaria ~1,3 s (1,68 → 0,41 s) num orçamento com 6 s de folga. Custaria reabrir ADR-0016 e ADR-0006. **Não fazer.** |
| **Modelo residente no worker** | estimado em 1–2 s | **~6 s por turn** (0,4 s de STT + 5,6 s de Kokoro). A estimativa estava baixa, não alta. **Fazer, e é decisão do CARD-009.** |

---

## 7. Pendências

| # | O que falta | Por que importa |
|---|---|---|
| 1 | Insumo com **voz real de aprendiz** | Sem ele não há coluna de qualidade honesta (§3.4) |
| 2 | ~~**Piper** como alternativa ao Kokoro~~ | **Resolvida na §9** (CARD-008): medido lado a lado, o Piper ganha em todos os eixos cronometrados |
| 3 | Reexecução em **máquina hospedada** | O número não transfere para x86 sem Neural Engine |
| 4 | Medição **ponta a ponta** (CARD-012) | O custo de composição da §1 continua desconhecido |
| 5 | Decidir se os scripts viram artefato do repositório | Benchmark que não se reexecuta vira folclore |

---

## 8. CARD-007 — mecanismo de saída estruturada e tempo até a primeira sentença

- **Medido em:** 2026-08-21, no CARD-007
- **Instrumentos:** `backend/benchmarks/llm_streaming_spike.py` (escolha do
  mecanismo) e `backend/benchmarks/llm_primeira_sentenca.py` (o número final,
  medido **através do adapter de produção**)
- **Insumo versionado:** prompt `v1.md`, `sha256:5903387004506a55…` (completo:
  `5903387004506a555b44692f81305ce91b3e31e693feac891a356ac9668551b7`); histórico
  de 6 trocas; falas curta (41 chars) e longa (291 chars, `sha256:924904ef26e86901`)
- **Custo total das duas execuções:** US$ 0,053 (`claude-haiku-4-5`)

> **Ressalva de método, aprendida no CARD-006:** o insumo está hasheado no
> próprio script e impresso na saída. Se o prompt mudar, o hash muda e as tabelas
> abaixo deixam de valer — explicitamente, não em silêncio.

### 8.1 Os quatro mecanismos (`llm_streaming_spike.py`)

Fala longa, 3 execuções úteis após 1 de aquecimento.

| Opção | TTFT p50 | 1ª fala legível p50 | Total p50 | `spoken_reply` 1º | Ordem estável |
|---|---|---|---|---|---|
| **A — tool use + `eager_input_streaming`** | 0,88 s | **0,88 s** | 3,72 s | **3/3** | **sim** |
| B — texto livre + parser parcial | 1,01 s | 1,04 s | 3,55 s | **2/3** | **não** |
| C — duas chamadas (só a da fala) | 0,55 s | 0,55 s | 1,65 s | 3/3 | sim (trivial) |
| D — `output_config.format` | 1,04 s | 1,35 s | 3,64 s | 3/3 | sim |

**O achado que decidiu o ADR-0030.** A rodada 3 da opção B produziu:

```
{"has_mistakes": true, "original": "So yesterday I was talki…
```

O modelo reordenou as chaves com o prompt pedindo a ordem explicitamente. É o
risco que o [ADR-0022](adr/0022-ordem-dos-campos-da-resposta-do-professor-e-contrato-de-latencia.md)
deixou em aberto, materializado em 1 de 3 execuções.

**Custo em tokens de entrada:** a opção A leva o schema da tool na requisição —
entrada de **1.473–1.522 tokens** contra **1.084** da linha de base da §5.1.
~400 tokens a mais por chamada, ~US$ 0,0004 no Haiku.

### 8.2 O número que o card existe para produzir (`llm_primeira_sentenca.py`)

Medido **através do `AnthropicTeacher`**, não de uma reimplementação: o número
inclui o parse incremental com `jiter` e o corte por sentença.

| Caso | 1ª sentença p50 | p95 | Resposta inteira p50 | Trechos emitidos |
|---|---|---|---|---|
| fala curta | **0,76 s** | 0,79 s | 2,05 s | 2 |
| fala longa | **0,68 s** | 0,82 s | 3,74 s | 3 |

**O custo do código próprio é ~0,05 s.** O TTFT medido na §5.1 é 0,60–0,73 s; a
primeira sentença sai praticamente junto com o primeiro token. O corte por
sentença paga por si com folga.

**O que a cascata recupera:** 1,29 s na fala curta e **3,06 s** na fala longa.

### 8.3 Relação com a §6

A tabela de alavancas da §6 marcou a cascata como "desnecessária" — conclusão
correta **dentro do orçamento daquele momento** (teto de 12–15 s, TTS Kokoro a
5,6 s). O alvo mudou para ~1,4 s de primeiro áudio
([`analise-caminho-para-1-2s.md`](analise-caminho-para-1-2s.md)), e com ele a
alavanca voltou — foi o que gerou os ADRs 0022, 0023 e 0026. **A §6 continua
verdadeira sobre o orçamento que mediu; ela não é a régua atual.**

---

## 9. CARD-008 — Kokoro vs Piper, medidos lado a lado

- **Data:** 2026-08-23 · **Máquina:** a mesma das §3–§5 (Apple M4)
- **Instrumentos:** `benchmarks/tts_kokoro.py` (inalterado) e
  `benchmarks/tts_piper.py` (novo), ambos sobre o protocolo do `_common.py` —
  aquecimento descartado, 5 repetições, percentil por posição sem interpolação.
- **Insumo idêntico e hasheado** (verificado por igualdade entre os dois
  módulos, não por inspeção visual):

  | Texto | Caracteres | SHA-256 (16) |
  |---|---|---|
  | `TIPICO` (resposta de 3–5 frases) | 276 | `a14ecf44376d35f1` |
  | `FRASE` (a primeira frase da cascata) | 61 | `0e6b159130536a29` |

O critério de comparação foi escrito no card **antes** da medição: tempo de
carga, RTF, número de dependências de sistema e qualidade percebida — com o
desempate declarado em favor do empacotamento em caso de empate na última.

### 9.1 Os números

Kokoro reproduziu a §4 quase exatamente (1,67 s vs. 1,68 s; RTF 0,098), o que
valida a comparação: a máquina e o protocolo não mudaram entre as duas sessões.

| Eixo | Kokoro (`af_heart`) | Piper (`en_US-lessac-medium`) | Razão |
|---|---|---|---|
| `import` do módulo | 2,45 s | **0,12 s** | 20× |
| Carga do modelo | 3,21 s | **0,43 s** | 7× |
| **Total até poder sintetizar** | **5,66 s** | **0,55 s** | **10×** |
| RTF | 0,098 | **0,024** | 4× |
| Primeira frase (61 chars) | 0,41 s | **0,09 s** | 4,5× |
| Resposta típica (276 chars) | 1,67 s | **0,35 s** | 4,8× |
| Taxa de amostragem | 24.000 Hz | 22.050 Hz | — |

A segunda voz medida (`en_US-amy-medium`) ficou dentro do ruído da primeira:
carga 0,44 s, RTF 0,024, primeira frase 0,10 s. A escolha de voz **não** é a
escolha de motor.

### 9.2 Empacotamento — o eixo que se decide sem cronômetro

| | Kokoro | Piper |
|---|---|---|
| Dependências de **sistema** | `espeak-ng` instalado no SO | **nenhuma** |
| Fonemização | `.dylib` externo, reapontado à mão **depois** do `import` | extensão compilada (`espeakbridge.so`) no próprio wheel |
| Dados de espeak | do sistema | **embarcados** (`piper/espeak-ng-data`) |
| Modelo de linguagem | spaCy + `en_core_web_sm` **não declarado** | não usa |
| Peso instalado | `torch` 501 MB + `spacy` 22 MB | `onnxruntime` 76 MB + `piper` 46 MB |
| `py.typed` | **não** | **sim** |
| Vozes | embarcadas no pacote | **download à parte** (60 MB por voz) |

**Observado ao vivo nesta sessão, e é o argumento mais forte da tabela:** rodar
o `tts_kokoro.py` num ambiente novo disparou **dois downloads não declarados no
meio da execução** — o `en_core_web_sm` (instalado pelo próprio spaCy, em
runtime) e os pesos do Hugging Face. Num container sem rede, isso não é lentidão:
é falha. O Piper não baixa nada em runtime; a voz é um artefato que se busca
explicitamente antes.

**A troca honesta:** o Piper não elimina o problema de artefato externo, ele o
**muda de natureza** — some a dependência de sistema (que vive no Dockerfile e
no `brew` de cada máquina), entra um par `.onnx` + `.onnx.json` versionado (que
vive num diretório e se baixa por comando). Trocar "três consertos de ambiente"
por "um download versionado" é bom negócio, mas é troca, não eliminação.

### 9.3 O que isso faz com o orçamento

Dois números do projeto mudam, e um ADR fica desatualizado:

1. **A carga do worker (ADR-0025) deixa de ser dominada pelo TTS.** Os ~6 s
   eram 5,63 s de Kokoro + 0,24–0,46 s de STT. Com o Piper, o total cai para
   **~1 s** — e o "restart custa ~6 s de fila parada" registrado como
   consequência aceita do ADR-0025 passa a ser falso na direção boa.
2. **O primeiro áudio.** Primeira sentença do LLM em 0,68–0,76 s (§8.2) mais
   **0,09 s** de síntese = **~0,8 s**, contra os ~1,1 s que o CARD-008 projetou
   com o Kokoro. O orçamento de 1,8 s deixa de ser apertado.

### 9.4 O que esta medição NÃO decide

**Qualidade percebida.** Nenhuma métrica automática de qualidade de voz foi
usada — inventar uma seria pior que admitir a lacuna, como na §3.4 sobre WER sem
voz de aprendiz. O julgamento é humano por natureza, e **foi feito**: as amostras
dos dois motores, mais uma correção pedagógica real sintetizada pelo adapter de
produção (`benchmarks/tts_audicao.py`), foram ouvidas pelo desenvolvedor em
2026-08-23, que aprovou a voz do Piper. Com isso, os quatro eixos do critério
escrito antes da medição estão cobertos, e o ADR-0032 deixa de ter lacuna.
