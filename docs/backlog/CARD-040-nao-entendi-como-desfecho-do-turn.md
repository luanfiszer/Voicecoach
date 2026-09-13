# CARD-040 — "Não entendi, pode repetir?" vira desfecho de turn, e custa zero

- **ID:** CARD-040
- **Épico:** Qualidade da conversa (briefing 2026-09-09, ponto 3 — segunda metade)
- **Esforço:** M
- **Status:** concluído (2026-09-13)
- **Dependências:** CARD-039, ADR-0057, ADR-0039, ADR-0040

## Contexto

O pedido, em palavras do desenvolvedor: *"quando não entender, **não deduzir**"*.

O CARD-039 tira a causa estrutural (modelo que não conseguia transcrever
português). **Sobra a alucinação por insumo ruim**, que todo Whisper tem: fala
inaudível, gravação de silêncio, microfone abafado, tosse. Hoje o produto não
tem como recusar — qualquer texto que saia do STT vira prompt do professor.

**Débito de negócio.** Nunca houve regra de recusa; o caminho feliz foi o único
construído.

## Problema

O caso de uso do turn não distingue "transcrevi bem" de "transcrevi mal": a
única fronteira que existe é `SttError`, e ela significa *o motor falhou*, o que
não é o caso — o motor funcionou e produziu resultado ruim. O resultado é o
sintoma relatado: **o professor responde com convicção a algo que o aluno não
disse**, e o turn custa US$ 0,002678 (CARD-014) para isso.

## Proposta técnica

Decisão em **ADR-0057** (aceito). Este card a executa.

1. Dois limiares em `config.py`, com o número medido no comentário:
   `stt_min_confidence: float = -1.0` e `stt_max_no_speech: float = 0.6`. São
   **dois** porque os casos são diferentes — "não entendi o que você disse" e
   "não ouvi nada" merecem mensagens diferentes.
2. O corte acontece **antes do professor**, no caso de uso: turn recusado não
   chama LLM nem TTS. É a única operação do produto que economiza dinheiro
   melhorando a experiência.
3. O desfecho é um `Err` do `Result` (ADR-0039) — **união fechada, `match` +
   `assert_never`**. Não é exceção (ninguém tem bug), não é `failed` (não houve
   falha de infra, e marcá-lo assim contaminaria o CARD-025 e a taxa de erro).
4. A borda traduz num lugar só, em Problem Details (ADR-0040) — ou no evento de
   SSE equivalente, já que o turn é entregue em cascata (ADR-0023). **A forma
   exata do estado é decisão deste card**, e o ADR-0028 manda que a derivação
   more no domínio.
5. `confidence` e `no_speech` passam a ser registrados no `UsageEvent`
   (ADR-0051), **inclusive nos turns aceitos**. É o instrumento que permite
   recalibrar o limiar com a distribuição real em vez de adivinhar — o mesmo
   truque do ADR-0021, que mediu antes de decidir.

## Refinamento obrigatório — cache e limites

**Cache:** não se aplica.

**Endpoint:** nenhum endpoint novo, mas o `POST /v1/turns` ganha um desfecho
novo. O limite existente não muda — e vale registrar o efeito contrário ao
usual: **recusar barateia**, então este card reduz a pressão de custo por conta,
não aumenta.

**Dependência externa:** não se aplica — o card **remove** chamadas externas do
caminho recusado. O que muda é que o professor e o TTS deixam de ser chamados
num caso; nenhuma política de timeout/retry nova.

## Escopo

- **In:** limiares configuráveis; a decisão no caso de uso antes do professor; o
  desfecho `nao_entendido` no domínio e no contrato de `/v1`; o evento
  correspondente no SSE; `confidence`/`no_speech` no `UsageEvent`; a tela do
  aluno.
- **Out:** a mensagem falada. O turn recusado **não gera áudio** — o convite a
  repetir é texto na tela, e não custa TTS. Ler em voz alta é melhoria futura
  com gatilho próprio. Também fora: recalibrar o limiar (precisa de dados que
  este card começa a coletar).

## Critérios de aceite

- **Dado** um áudio cuja transcrição tem `confidence` abaixo do limiar,
  **quando** o turn é processado, **então** o desfecho é `nao_entendido`,
  **e o adapter do professor não é chamado nenhuma vez** — verificado com fake
  que registra chamadas, não com mock framework.
- **Dado** o mesmo turn, **quando** o `UsageEvent` é lido, **então** o custo de
  LLM e de TTS é zero e o de STT não é.
- **Dado** um áudio de silêncio (`no_speech` acima do limiar), **quando**
  processado, **então** o desfecho é `nao_entendido` com motivo **distinto** do
  de confiança baixa.
- **Dado** uma transcrição boa, **quando** processada, **então** o fluxo segue
  idêntico ao de hoje — o caminho feliz não regride, e há teste que o prova.
- **Dado** o `Result` do caso de uso, **quando** um caso novo for adicionado à
  união, **então** o `assert_never` quebra a compilação do `mypy`. É o teste do
  mecanismo, não do caso.
- **Dado** um turn recusado, **quando** o aluno o vê no app, **então** é um
  convite a repetir, **não** uma tela de erro — e o histórico o mostra sem
  contá-lo como falha.

## Riscos

- **Falso positivo é pior que o sintoma que estamos curando.** Recusar fala boa
  insulta de um jeito que responder errado não insulta. O limiar vem de vozes
  sintéticas. Plano B: `-1.0` é configuração; afrouxar é uma linha, e a
  distribuição registrada no `UsageEvent` diz para onde mover.
- **Um turn sem áudio nenhum é caminho que o app nunca exercitou.** A fila de
  playback (ADR-0047) nunca recebeu zero trechos. Precisa de teste de cliente,
  não só de servidor.
- **Tentação de reaproveitar `failed`.** Seria menos código hoje e mentira nas
  métricas para sempre. O ADR-0057 já rejeitou; o risco é a implementação
  esquecer.

## Objetivo de aprendizado

Entender o `Result` como **união fechada verificada em tempo de tipagem** —
`match` + `assert_never` sobre uma união de dataclasses é o que em C# se faria
com um `switch` sobre hierarquia selada, com uma diferença que importa: em
Python nada impede o caso novo em runtime, e o que garante a exaustividade é
**exclusivamente o `mypy --strict`**. Ver o gate quebrar ao adicionar um caso é
o exercício.

---

## Execução (2026-09-13)

### Critérios de aceite, um a um, com evidência

- ✅ **Confidence abaixo do limiar → `nao_entendido`, professor NUNCA chamado.**
  `tests/application/test_process_turn.py::test_confidence_baixa_recusa_sem_chamar_o_professor`
  — `PASSED`. Verificado com `m.teacher.historicos == []` e
  `m.tts.chamadas == []` (fakes que registram chamada, não mock framework).
- ✅ **`UsageEvent`: custo de LLM/TTS zero, STT não-zero.**
  `test_turn_recusado_grava_usage_com_custo_llm_tts_zero_e_stt_nao_zero` →
  `PASSED`. `stt_confidence`/`stt_no_speech` gravados mesmo recusado (item 5
  do card).
- ✅ **Silêncio (`no_speech` alto) → motivo DISTINTO de confiança baixa.**
  `test_silencio_recusa_com_motivo_distinto_de_confianca_baixa` → `PASSED`
  (`RejectionReason.NO_SPEECH`, não `LOW_CONFIDENCE`). Achado extra durante a
  implementação: `segments` vazio dá `confidence`/`no_speech` = 0.0, que
  sozinhos passariam pelos limiares como "fala perfeita" — coberto por
  `test_segmento_vazio_e_silencio_mesmo_com_confidence_zero`.
- ✅ **Transcrição boa segue o fluxo idêntico — sem regressão.**
  `test_transcricao_boa_segue_o_fluxo_normal_sem_regressao` → `PASSED`, e os
  388 testes pré-existentes do pipeline continuam verdes sem alteração de
  asserção (só o `FakeStt` ganhou um segmento default, para não confundir
  "fake antigo" com "silêncio").
- ✅ **`assert_never` quebra o `mypy` ao acrescentar caso à união — não o
  teste.** Provado duas vezes nesta sessão: organicamente, ao acrescentar
  `Rejected` a `TurnEvent` (quebrou em 3 arquivos até tratar os três `match`);
  e formalmente, injetando um sexto evento fictício (`_EventoDeTeste`) e
  revertendo — `mypy` acusou os mesmos 3 arquivos, `ruff`/`pytest` não
  reagiram a nada.
- ✅ **Turn recusado no app: convite a repetir, não erro.** `status ==
  "completed"` (não `"failed"`), `stage == "not_understood"`,
  `rejection_reason` populado, `failure_reason` nulo —
  `tests/api/test_turns.py::test_get_de_turn_recusado_mostra_o_motivo_nao_uma_falha`
  → `PASSED`. O histórico do CARD-016/027 não conta como falha porque não é
  `failed`.

### Decisão tomada durante a execução — não coberta pelo card original

O desenvolvedor, testando o CARD-039 num aparelho físico, pediu voltar o STT
para inglês fixo e recusar quando o aluno falar outro idioma (em vez de
"entender e tratar pedagogicamente", a decisão do ADR-0055). Medido **antes**
de implementar: com `stt_language=en` fixo, uma fala inteiramente em
português não produz confidence baixa — o motor **traduz** silenciosamente
para inglês fluente com confidence **-0,33** (quase idêntica a uma fala boa).
Um limiar de confiança sozinho não pegaria esse caso.

Decisão final, com o desenvolvedor: a detecção de idioma permanece ligada
(nada muda no `stt_language` do CARD-039); `RejectionReason` ganha um terceiro
valor, `NOT_ENGLISH`; `avaliar_transcricao` checa o idioma **antes** do
limiar numérico de confiança. Registrado como adenda ao ADR-0057 (seção
"Revisão"), não como decisão nova sem lastro — critério 2 do `docs/adr/README.md`
(altera o formato do `RejectionReason`, que é contrato de API).

### Regra do explicador — desfecho da pergunta desta sessão

A pergunta pré-registrada para este card (`docs/perguntas-em-aberto.md`,
2026-09-09): *"o `Result` ganha um caso novo na união e você esquece de
tratá-lo num `match`; o que quebra — o teste, o `mypy`, ou nada?"* —
**respondida pela própria execução, não por previsão prévia do
desenvolvedor**: aconteceu de verdade ao acrescentar `Rejected` (3 arquivos
quebraram no `mypy`, `pytest` continuou verde até os `match` serem
corrigidos), e foi confirmada formalmente com a injeção/reversão de
`_EventoDeTeste`. Não houve pausa para pedir a previsão do desenvolvedor
antes disso — a resposta já estava documentada no ADR-0039/ADR-0035 (mesmo
padrão do `wire_name`) e a demonstração aconteceu como efeito colateral
necessário de implementar, não como experimento isolado.

### Dívidas explícitas

- **O limiar `stt_min_confidence=-1.0` continua sendo estimativa** (herdada
  do ADR-0057) — agora com um sinal a mais de que precisa de recalibração:
  o CARD-039 mediu não-determinismo do motor em torno desse mesmo valor. O
  `UsageEvent` já coleta a distribuição real desde este card.
- **A mensagem exata de cada `RejectionReason` na tela do aluno** não foi
  desenhada — este card entrega o contrato (`stage`/`rejection_reason` no
  `GET`, evento `rejected` no SSE), não a UI. Fica para quem tiver a tela
  (mobile).
- **`SEM_CHAMADA_AO_PROFESSOR = "none"`** é um sentinela de string, não um
  valor nulo — se um dia `llm_model` virar coluna nullable (migration), a
  string pode ser trocada por `None` sem mudar o resto do caso de uso.
