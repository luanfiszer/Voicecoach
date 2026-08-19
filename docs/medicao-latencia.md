# Medição de latência e custo dos componentes de IA

- **Data:** 2026-08-19
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
| 2 | **Piper** como alternativa ao Kokoro | O Kokoro traz três dependências de sistema (§4.3) |
| 3 | Reexecução em **máquina hospedada** | O número não transfere para x86 sem Neural Engine |
| 4 | Medição **ponta a ponta** (CARD-012) | O custo de composição da §1 continua desconhecido |
| 5 | Decidir se os scripts viram artefato do repositório | Benchmark que não se reexecuta vira folclore |
