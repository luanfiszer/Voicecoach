# CARD-039 — O STT ouve qualquer idioma, e a porta para de jogar fora o que ele produz

- **ID:** CARD-039
- **Épico:** Qualidade da conversa (briefing 2026-09-09, ponto 3 — primeira metade)
- **Esforço:** M
- **Status:** backlog
- **Dependências:** ADR-0055, ADR-0056 (ambos escritos)

## Contexto

Primeiro uso em aparelho físico (CARD-037), terceiro apontamento: *o professor
entende errado, e inventa inglês quando o aluno fala português*.

**Débito de negócio, não técnico.** O código está correto para a regra que lhe
foi dada — "o aluno fala inglês por definição", escrito no comentário do
`faster_whisper_adapter.py`. A regra é que estava errada: um brasileiro
iniciante fala português no meio da frase o tempo todo. Não há nada a refatorar;
há um requisito a corrigir.

A causa foi medida na investigação de 2026-09-09 e está inteira no ADR-0055,
junto com o que ela **derrubou** (o `beam_size` não tem nada a ver com o
sintoma — ele nem existe no adapter que roda nesta máquina).

## Problema

Três fatos que se somam:

1. `config.py:322-323` — os modelos são `small.en` e
   `whisper-small.en-mlx`, as variantes *English-only*. Diante de português,
   produzir inglês inventado **é o comportamento correto delas**.
2. `mlx_whisper_adapter.py:27` e `faster_whisper_adapter.py:38` —
   `LANGUAGE = "en"` é constante de módulo. Nem configuração é.
3. `application/ports/speech_to_text.py` — `Transcript` guarda `text`,
   `language`, `duration_seconds` e **descarta** o `avg_logprob`, o
   `no_speech_prob` e os segmentos com `start`/`end` que o Whisper já calculou.

Evidência colada, mesmo áudio, duas execuções:

```
pt1.aiff  ->  'Comment SHARE Tooth imitate'                             avg_logprob=-5.938
pt1.aiff  ->  'And if you like this video, please like and subscribe.'  avg_logprob=-1.124
en1.aiff  ->  'Yesterday I go to the market to buy some bread, …'       avg_logprob=-0.143
```

## Proposta técnica

Decisões já registradas: **ADR-0055** (modelo multilíngue + idioma detectado) e
**ADR-0056** (a forma nova do `Transcript`). Este card os executa.

1. `stt_model_mlx = "mlx-community/whisper-small-mlx"` e
   `stt_model_faster_whisper = "small"`. **O porte não muda** — o ADR-0027 item
   7 segue bloqueando `medium`.
2. `LANGUAGE` sai dos dois adapters; entra `stt_language: str | None = None`
   em `config.py`, onde `None` significa detectar. Um campo só (ao contrário do
   nome do modelo, que são dois por bom motivo).
3. `Transcript` ganha `confidence`, `no_speech` e `segments: tuple[Segment, ...]`.
   `Segment` é value object do projeto — **nenhum tipo de biblioteca atravessa**
   (mesma regra do ADR-0029, agora na saída).
4. A média de `avg_logprob` ponderada por duração é feita **no adapter**, porque
   é ele que conhece o formato de cada motor.
5. O `import-linter` ganha a garantia correspondente: nada de `numpy`, `dict` do
   `mlx` ou segmento do `faster-whisper` visível em `application`.

**O comentário de cada constante removida vira comentário do campo novo** — o
projeto trata comentário de medição como parte da medição, e apagar o "medido em
§3.2" ao mover a constante seria desfazer o registro.

## Refinamento obrigatório — cache e limites

**Cache:** não se aplica ao dado, mas se aplica aos **pesos**. Os modelos
multilíngues são download novo (~500 MB no `small` do mlx) e ficam no cache do
Hugging Face. TTL: indefinido — pesos são imutáveis por revisão. Invalidação:
troca do identificador do modelo na configuração. O worker mantém o modelo
**residente** (ADR-0025) e a readiness só fica verde depois da carga — um worker
que suba sem os pesos novos deve falhar, não degradar.

**Endpoint:** não se aplica — nenhum endpoint muda.

**Dependência externa:** o download dos pesos é a única, e acontece **na subida,
não no turno**. Timeout: o do `huggingface_hub`, herdado. Idempotente: sim, é
cache por revisão. Desfecho quando falha: readiness vermelha e o worker não
aceita jobs — que é o comportamento já estabelecido pelo ADR-0025, e o certo:
worker que aceita o que não consegue completar é pior que worker fora.

## Escopo

- **In:** troca de modelo nos dois adapters; `stt_language` configurável;
  `Transcript` e `Segment` na forma do ADR-0056; normalização de `confidence`
  nos dois adapters; migração de todos os fakes de teste; medição de latência
  refeita e registrada em `docs/medicao-latencia.md`.
- **Out:** o **uso** dos campos novos. O limiar de confiança é o CARD-040; o
  idioma chegando ao professor é o CARD-041; os `segments` entram **sem
  consumidor de propósito** (ADR-0056, alternativa C). Subir para `medium`
  segue bloqueado.

## Critérios de aceite

- **Dado** um áudio falado em português, **quando** transcrito com a
  configuração default nova, **então** `transcript.language == "pt"` e o texto
  corresponde ao que foi dito — verificado com o insumo em português commitado
  em `tests/fixtures/stt/`.
- **Dado** o mesmo áudio, **quando** transcrito com `stt_language="en"`,
  **então** `language == "en"` — provando que o campo governa, e que o recuo
  barato do ADR-0055 funciona sem recompilar.
- **Dado** uma transcrição correta em inglês, **quando** lida, **então**
  `confidence > -1.0`; **dado** o áudio em português transcrito pelo modelo
  `.en` antigo, **então** `confidence < -1.0`. É o teste que **prova o limiar**
  que o CARD-040 vai usar, e ele é o motivo de o insumo em português ser
  commitado.
- **Dado** um `Transcript` de fala com pausas, **quando** lido, **então**
  `segments` tem mais de um elemento com `end_seconds` crescentes.
- **Dado** o adapter em execução, **quando** `lint-imports` roda, **então**
  nenhum tipo de `numpy`/`mlx`/`faster_whisper` alcança `application`.
- **Dado** os cinco insumos de `docs/medicao-latencia.md`, **quando** remedidos,
  **então** o número novo está no documento — inclusive se for pior que o
  previsto. Número honesto vale mais que número bom (ADR-0048).

## Riscos

- **A medição foi feita com voz sintética.** Ela prova o mecanismo, não o acerto
  sobre sotaque brasileiro real. Plano B: se o multilíngue errar mais em fala
  real, o recuo é `stt_language="en"` no `.env` — uma linha, sem deploy.
- **Detecção errada em fala curta.** Um "pt" falso positivo num "yes" faria o
  professor tratar inglês como português. Mitigado pelo ADR-0059 item 3 (o
  idioma é dica, não comando) e por não haver consumidor ainda neste card.
- **+0,17 s no caminho crítico**, num orçamento já estourado (3,04 s contra alvo
  de 2,4 s). Declarado e aceito no ADR-0055; o número precisa aparecer na
  medição, não ser esquecido.
- **A porta muda e todo fake quebra de uma vez.** É esperado — `mypy --strict`
  vai listar todos. Não é risco, é o gate funcionando.

## Objetivo de aprendizado

Entender **por que um `Protocol` alargado quebra tudo de uma vez, e por que isso
é a propriedade desejável** — em C# uma interface com membro novo se resolveria
com implementação default e ninguém notaria; aqui a tipagem estrutural + `mypy
--strict` transforma "alarguei o contrato" numa lista completa de quem precisa
mudar, sem herança e sem registro. É a diferença entre acoplamento por
declaração e acoplamento por forma, sentida na prática.
