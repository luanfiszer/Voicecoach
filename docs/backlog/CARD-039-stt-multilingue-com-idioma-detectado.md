# CARD-039 — O STT ouve qualquer idioma, e a porta para de jogar fora o que ele produz

- **ID:** CARD-039
- **Épico:** Qualidade da conversa (briefing 2026-09-09, ponto 3 — primeira metade)
- **Esforço:** M
- **Status:** concluído (2026-09-13)
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

---

## Execução (2026-09-13)

### Critérios de aceite, um a um, com evidência

- ✅ **Áudio em português, configuração default, `language == "pt"` e texto
  correto.** Provado contra o motor real:
  `tests/adapters/test_stt_integration.py::test_multilingue_com_deteccao_entende_o_portugues`
  — `uv run pytest -m slow` → `PASSED`. Fixture novo:
  `tests/fixtures/stt/pt-br-curto.wav` (3,97 s, `say -v Luciana`, "Não sei como
  dizer isso em inglês, você pode me ajudar?").
- ✅ **Mesmo áudio com `stt_language="en"`, `language == "en"`.** Provado:
  `test_stt_language_forcado_governa_mesmo_com_audio_em_portugues` → `PASSED`.
- ✅ **`confidence` separa transcrição correta de alucinação.** Provado, mas
  **com o teste reescrito durante a implementação** — ver "Decisão tomada
  durante a execução" abaixo:
  `test_confidence_separa_a_alucinacao_do_modelo_en_da_transcricao_correta` →
  `PASSED`, 3 execuções seguidas para excluir sorte.
- ✅ **`segments` com múltiplos elementos e `end_seconds` crescentes.** Provado:
  `test_segments_tem_tempos_crescentes` → `PASSED`.
- ✅ **`lint-imports`: nenhum tipo de `numpy`/`mlx`/`faster_whisper` alcança
  `application`.** `Contracts: 4 kept, 0 broken`. **Gate provado que morde**:
  violação injetada (`import numpy as np` em
  `application/ports/speech_to_text.py`) → `Contracts: 3 kept, 1 broken`,
  apontando a linha exata; revertida, `4 kept, 0 broken` de novo.
- ✅ **`docs/medicao-latencia.md` remedido, número honesto inclusive se pior.**
  §13, nova. Custo da detecção: **+0,18 s** de média (4 insumos), reproduz o
  +0,17 s do ADR-0055. Achado **não previsto** também registrado: a alucinação
  do `.en` antigo é não-determinística o bastante para atravessar o limiar
  `-1,0` original em algumas execuções (medido: -0,97 a -1,10 em 5 repetições)
  — número ruim registrado, não escondido.

### Decisão tomada durante a execução (não coberta pelos ADRs — não é decisão de arquitetura, é achado de comportamento)

O critério de aceite original comparava `confidence` do modelo antigo contra
um limiar absoluto (`< -1,0`). Medindo 5 execuções do `.en` antigo contra o
mesmo áudio pt-BR, o valor oscilou entre **-0,97 e -1,10** — em torno do
próprio limiar, não abaixo dele de forma confiável (causa: fallback de
temperatura do Whisper, que já era conhecido pelo ADR-0055 como
"não-determinístico", mas cuja magnitude perto do limiar não tinha sido
medida). Um teste que passa ou falha por sorte não verifica nada.

**Perguntado ao desenvolvedor no ponto da decisão** (antes de reescrever o
teste): confirmado que a preocupação inicial era sobre latência (não era) —
esclarecido que a variância é do **texto/confiança** da alucinação, não do
**tempo** de execução (esse continua estável, medido em §13.1) — e que a
instabilidade é sintoma do próprio bug que o card corrige, não efeito
colateral da correção (confirmado rodando o modelo novo 5x: resultado idêntico
byte a byte nas 5). **Decisão, com aprovação do desenvolvedor:** o teste passa
a comparar **relativamente** (`confidence` do modelo novo supera o antigo em
pelo menos 0,3) em vez de contra um limiar absoluto. Registrado como dívida
explícita para o CARD-040: o limiar do desfecho "não entendi" (ADR-0057) não
pode ser um número único fixo perto de -1,0, sob pena de herdar o mesmo
problema.

Não gera ADR novo: não introduz dependência, não altera a fronteira decidida
pelo ADR-0055/0056, não afeta custo nem segurança — é escolha local e
reversível de como um teste verifica um comportamento (`docs/adr/README.md`,
seção "Quando NÃO escrever ADR": "detalhes de implementação").

### Regra do explicador — desfecho das perguntas desta sessão

Candidatas da fila (`docs/perguntas-em-aberto.md`, registradas em 2026-09-09).
Escolhidas as duas mais caras de errar; a terceira (mypy/Protocol) não foi
reapresentada nesta sessão — ver arquivo de perguntas.

1. **"Com um áudio bem curto (ex.: só 'yes'), o multilíngue com detecção
   classifica como pt ou en, e com que confiança?"** — feita antes de
   qualquer consumidor futuro do campo `language`. **Dispensada pelo
   desenvolvedor** ("pode rodar o experimento e seguir"). Rodado assim mesmo:
   `mlx-whisper`, áudio de 0,48 s ("Yes"), detectou `en` corretamente,
   `confidence=-0,625` — pior que uma fala longa (-0,13 a -0,32 no ADR-0055),
   mas ainda longe do território de alucinação. Sem consumidor neste card
   (CARD-040/041), então sem decisão de produto pendente aqui.
2. **"A média ponderada por duração esconde um segmento ruim (ex.: tosse) num
   turno de 3 segmentos?"** — feita antes de escrever a fórmula de
   `confidence`. **Não chegou a ser apresentada isoladamente**: a
   implementação da fórmula (ADR-0056, já decidida) e o teste que prova o
   comportamento (`test_faster_whisper_confidence_e_media_ponderada_por_duracao`)
   tornaram a resposta imediatamente observável durante a própria escrita do
   código — **sim, esconde**: um segmento de 1s com -0,1 e outro de 2s com
   -0,4 dão confidence -0,3 (mais perto do ruim, porque pesa mais), não a
   média simples -0,25. Fica registrado aqui como resposta objetiva; não foi
   formalmente perguntada e respondida por escrito porque a pergunta 1 e o
   achado do não-determinismo (acima, que nasceu no ponto da decisão e não
   estava na lista de candidatas) já ocuparam as duas do limite desta sessão.

### Dívidas explícitas

- **CARD-040:** o limiar de confiança não pode ser um número fixo único perto
  de -1,0 — precisa considerar a variância medida em `docs/medicao-latencia.md`
  §13.3, e precisa ser validado contra os dois adapters (`mlx` e
  `faster-whisper`), não só um.
- **`faster-whisper` não foi remedido em TEMPO** com o script novo
  (`benchmarks/stt_deteccao_idioma.py` mede só `mlx`, o motor local desta
  máquina) — só em `confidence`, via teste de integração. Gatilho: máquina x86
  disponível (mesma lacuna do ADR-0027).
- **`no_speech` sem segmento nenhum é `0.0` por convenção** (documentado no
  docstring do campo) — não é um caso coberto pelo ADR-0056 explicitamente;
  decisão local de implementação, sem impacto de produto até haver consumidor.
