# ADR-0032 — Piper substitui o Kokoro como motor de voz local

- **Status:** aceito
- **Data:** 2026-08-23
- **Relacionado:** [ADR-0011](0011-stt-e-tts-locais-como-default.md) (que elegeu
  o Kokoro como candidato principal e o Piper como fallback),
  [ADR-0025](0025-modelos-residentes-no-worker-e-readiness-que-distingue-pronto.md)
  (cujo número de carga muda por causa desta decisão), ADR-0010, CARD-008
- **Consome:** [`medicao-latencia.md`](../medicao-latencia.md) §9
- **Critérios de obrigatoriedade:** **1 — troca uma dependência externa** (o
  motor de TTS e toda a árvore que ele arrasta).

## Contexto

O ADR-0011 escolheu TTS local e nomeou o Kokoro como candidato principal, com o
Piper como fallback — **sem medir nenhum dos dois**, porque naquele momento não
havia instrumento. A escolha era declaradamente provisória: *"a promoção de um
default é decisão medida, não estética"*.

Duas coisas mudaram desde então. A medição de 2026-08-19 (§4) cronometrou o
Kokoro e encontrou **5,63 s de carga** — o dono dos ~6 s que o ADR-0025 aceitou
como custo de subida do worker — além de três dependências de sistema que não
apareciam em lugar nenhum do `pyproject.toml`. E o CARD-008 mediu o Piper com o
mesmo protocolo, o mesmo insumo e a mesma máquina (§9).

O critério de comparação foi escrito **antes** da medição, no card: tempo de
carga, RTF, número de dependências de sistema e qualidade percebida — com o
desempate declarado em favor do empacotamento em caso de empate na última.

## Decisão

**O Piper passa a ser o motor de TTS do produto. O Kokoro sai do caminho
default, permanece nomeado no enum `TtsProvider` e não tem adapter.**

1. **`TTS_PROVIDER=piper` é o default**, e `piper-tts` entra como dependência
   base (não como extra de plataforma, ao contrário do `mlx-whisper`): ele
   publica wheels para macOS arm64, Linux x86_64/aarch64 e Windows.
2. **`TTS_PROVIDER=kokoro` levanta na subida** com uma mensagem que nomeia as
   três dependências de sistema. Não existe adapter pela metade: é a mesma
   regra do `STT_PROVIDER=openai` (ADR-0027) — código que nunca pode ser
   exercitado não entra.
3. **A voz é configuração** (`TTS_VOICE`, `TTS_VOICES_DIR`), e o arquivo tem de
   existir antes: voz ausente **falha no boot**, dizendo o comando que a baixa.
4. **`py.typed`:** o Piper publica, então — ao contrário de `boto3`,
   `faster_whisper` e `asyncpg` — **não** precisa de override no `mypy`.

### O que a medição diz (§9, mesma máquina, mesmo insumo hasheado)

| Eixo | Kokoro | Piper | Razão |
|---|---|---|---|
| Total até poder sintetizar | 5,66 s | **0,55 s** | **10×** |
| RTF | 0,098 | **0,024** | 4× |
| Primeira frase (61 chars) | 0,41 s | **0,09 s** | 4,5× |
| Dependências de sistema | 3 | **0** | — |
| Peso instalado | torch 501 MB + spaCy 22 MB | onnxruntime 76 MB + piper 46 MB | ~5× |

**O argumento que não é sobre velocidade:** rodar o Kokoro num ambiente limpo
disparou **dois downloads não declarados em runtime** — o `en_core_web_sm`
(instalado pelo próprio spaCy, durante a execução) e os pesos do Hugging Face.
Num container sem rede de saída, isso não é lentidão: é falha. O Piper não baixa
nada sozinho; a voz é um artefato buscado explicitamente antes.

## Alternativas consideradas

### Alternativa A — Manter o Kokoro e resolver o empacotamento no Dockerfile

- **O que é:** aceitar as três dependências de sistema e instalá-las na imagem
  (`apt-get install espeak-ng`, o modelo do spaCy num `RUN`, o reaponte do
  `EspeakWrapper` no código do adapter).
- **Por que foi rejeitada:** resolveria o empacotamento e **não** os 5,66 s de
  carga nem o RTF 4× pior. Pagaria uma imagem com torch (501 MB) para rodar um
  modelo de 82M de parâmetros, e manteria o reaponte do `EspeakWrapper` — um
  conserto que depende da ordem de import de uma biblioteca de terceiros, que é
  precisamente o tipo de acoplamento que quebra em silêncio numa atualização.

### Alternativa B — Manter os dois adapters, como no STT (ADR-0027)

- **O que é:** dois motores atrás da porta, escolhidos por config, como
  `mlx-whisper` e `faster-whisper`.
- **Por que foi rejeitada:** no STT os dois adapters existem porque **nenhum dos
  dois roda em toda plataforma** — é uma restrição de ambiente, não uma
  preferência. Aqui o Piper roda em todo lugar e ganha em todos os eixos
  medidos: o segundo adapter seria código sem pergunta a responder, com o custo
  de manter viva uma árvore de dependências de 500 MB. É a peça que a visão §F
  manda cortar.

### Alternativa C — OpenAI TTS (o modo qualidade do ADR-0011)

- **O que é:** desistir do local e pagar ~US$ 0,005/turn.
- **Por que foi rejeitada:** contraria o ADR-0010 (gasto restrito ao Claude) e
  acrescenta latência de rede no caminho crítico. Continua disponível por
  configuração no dia em que a qualidade da voz for medida como insuficiente —
  que é exatamente a lacuna registrada abaixo.

## Consequências

**Positivas**

- **O ADR-0025 fica melhor do que foi escrito.** A carga do worker cai de ~6 s
  para **~1 s** (0,43 s de voz + 0,24–0,46 s de STT), e a consequência aceita
  "todo restart custa ~6 s de fila parada" deixa de valer. O ADR-0025 **não é
  substituído**: sua decisão (modelo residente, readiness que distingue "subiu"
  de "pronto") continua inteira — só o número que a motivou encolheu.
- **O primeiro áudio cabe no orçamento com folga:** 0,68–0,76 s da primeira
  sentença (§8.2) + **0,09 s** de síntese ≈ **0,8 s**, contra o alvo de 1,8 s.
- **O Dockerfile do worker (CARD-009) fica trivial** no que toca ao TTS: nenhum
  pacote de sistema, nenhum modelo de spaCy, nenhuma ordem de import a respeitar.
- **A troca custou uma linha de configuração**, e essa é a primeira cobrança
  real do investimento em portas (ADR-0011, item 4): trocar o motor inteiro não
  tocou `domain`, `application` nem consumidor nenhum.

**Negativas — o preço aceito**

- ~~**A qualidade percebida NÃO foi julgada.**~~ **Fechado em 2026-08-23**, no
  mesmo dia: o desenvolvedor ouviu as amostras dos dois motores — incluindo uma
  correção pedagógica real, com contraste de forma errada/certa e pergunta ao
  final — e aprovou a voz do Piper (`en_US-lessac-medium`, o default). O
  critério escrito antes da medição exigia empate em qualidade para o desempate
  por empacotamento valer; o julgamento tornou a exigência desnecessária, porque
  não houve nada a desempatar. **Este ADR deixa de ter lacuna conhecida.**
  Gatilho para reabrir permanece: uso prolongado revelar prosódia insuficiente
  em sessão longa — o custo de reverter é uma linha de config mais um adapter de
  ~40 linhas.
- **A voz deixa de vir no pacote.** São 60 MB por voz, baixados por comando, que
  precisam existir no container do CARD-009 e na máquina de quem clona o repo.
  Trocamos três dependências de sistema por **um artefato versionado** — é troca,
  não eliminação, e ela move o problema do `apt`/`brew` para o build da imagem.
- **`en_US-lessac-medium` vs. `en_US-amy-medium` não foi um julgamento
  comparativo.** As duas foram cronometradas (dentro do ruído uma da outra) e
  ouvidas, e a aprovação recaiu sobre o default sem que a segunda fosse
  rejeitada explicitamente. Trocar de voz é uma linha de configuração.
- **O Kokoro fica no enum sem adapter**, o que é uma promessa parcial: quem ler
  a configuração vai supor que `kokoro` funciona. Mitigado pela mensagem de erro,
  que nomeia as três dependências e aponta o ADR.

**Equivalente mental .NET:** trocar um pacote que exige um runtime nativo
instalado na máquina (e um `LD_LIBRARY_PATH` certo) por outro que embarca a
dependência nativa no próprio NuGet — mesma interface, o `Dockerfile` encolhe, e
o modelo passa a ser um asset versionado em vez de um `apt-get`.
