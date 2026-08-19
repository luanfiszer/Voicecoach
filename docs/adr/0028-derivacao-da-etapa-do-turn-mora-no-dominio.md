# ADR-0028 — A derivação da etapa do Turn mora no domínio, não na borda

- **Status:** aceito
- **Data:** 2026-08-19
- **Relacionado:** [ADR-0023](0023-ciclo-de-vida-do-turn-com-entrega-em-cascata.md)
  (define a tabela), [ADR-0016](0016-ciclo-de-vida-do-turn-estado-grosso-e-etapa-derivada.md)
  (substituído; é a origem da regra que este ADR revoga), ADR-0003, ADR-0008,
  ADR-0012
- **Critérios de obrigatoriedade** (`docs/adr/README.md`): **6 — contraria uma
  convenção estabelecida**. O ADR-0016 §4 escreveu que a derivação mora *"na
  borda (`api/schemas`)"*, e a skill `voicecoach-arquitetura` repete isso. Este
  ADR muda o lugar. (O critério **2** também toca o tema, mas já está registrado
  no ADR-0023 — o conteúdo da tabela é dele; aqui só se decide **onde** ela é
  calculada.)

## Contexto

O ADR-0016 decidiu duas coisas em um item só, e elas se separaram depois:

1. **O quê:** a etapa exibida ao aluno é **derivada** dos artefatos, nunca
   persistida.
2. **Onde:** *"A derivação mora no servidor, na borda (`api/schemas`, CARD-010),
   **nunca no cliente** — senão a mesma regra é reimplementada no mobile e na web
   e as duas divergem."* (ADR-0016 §4)

O ADR-0023 substituiu o ADR-0016 por causa da entrega em cascata. Ele
**reescreveu a tabela** de derivação (item 4, com `speaking` passando a depender
da existência de trechos em vez de `reply_text`) e **ficou silencioso sobre o
lugar**. O CARD-018, que implementa o ADR-0023, esbarrou nesse buraco na
primeira linha de código: `Turn.stage` é propriedade da entidade ou função do
schema de resposta?

O contexto mudou o suficiente para que a resposta de 2026-08-18 não se herde
automaticamente:

- **A regra deixou de ser sobre uma coluna e passou a ser sobre uma coleção.**
  "Existe ao menos um trecho?" é pergunta sobre o agregado `Turn`, não sobre o
  DTO — e o DTO só a responde porque alguém carregou a coleção antes.
- **O ADR-0023 tornou o teste da tabela obrigatório**, não recomendável
  (*"o teste da tabela de derivação passa a ser obrigatório"*, §Consequências).
  Uma regra obrigatória de testar que mora na borda arrasta FastAPI para dentro
  de um teste que é lógica pura.
- **O ADR-0019** cobra ≥ 90% de cobertura de `domain` + `application`, e 80%
  global com folga *porque a borda oscila*. Pôr lógica obrigatória na camada
  com a régua mais frouxa é empurrar o que é caro de errar para onde se mede
  menos.

## Decisão

**`Turn.stage` e `Turn.delivered_partially` são propriedades calculadas da
entidade de domínio. A borda projeta o valor; não o computa.**

1. `TurnStage` é uma `StrEnum` em `domain/turn.py`, com o mesmo vocabulário do
   ADR-0016 (`transcribing`, `thinking`, `speaking`, `completed`) e a ordem de
   avaliação do ADR-0023 item 4.
2. O schema de resposta do `GET /v1/turns/{id}` (CARD-010) lê `turn.stage` e o
   serializa. **Nenhum `if` sobre artefato vive em `api/schemas`.**
3. **A intenção original do ADR-0016 §4 é preservada e reforçada:** continua
   havendo **uma** implementação, no servidor, e o cliente continua proibido de
   reimplementá-la. O que muda é a camada dentro do servidor — de `api` para
   `domain`.
4. Nada é persistido. A proibição do ADR-0016/0023 contra coluna `stage` ou
   `delivered_partially` continua integralmente de pé, e é o que este ADR **não**
   toca.

### Por que isto não fere a regra de camada (ADR-0012)

`TurnStage` é uma `StrEnum` da stdlib. O `domain` continua importando só a
stdlib, e `uv run lint-imports` continua verde sem contrato novo. O que a
entidade ganha é vocabulário, não dependência.

## Alternativas consideradas

### Alternativa A — Manter a derivação na borda (`api/schemas`), como o ADR-0016 escreveu

- **O que é:** a entidade expõe `audio_chunks`, `transcript` e
  `reply_audio_ref`; o schema pydantic de resposta faz a cadeia de `if` e emite
  o campo `stage`.
- **A favor:** fidelidade literal ao ADR-0016; e um argumento real — `stage` é
  vocabulário de **apresentação** ("professor pensando" é o que a tela diz, não
  o que o negócio sabe), e o ADR-0003 já classifica a borda como a camada
  descartável no V2, o que faria dela o lugar natural de algo que muda com a UI.
- **Por que foi rejeitada:** três custos concretos. (1) O teste obrigatório da
  tabela passa a exigir rota HTTP para exercitar quatro `if` — e o CARD-018
  precisaria subir o app para provar seu principal critério de aceite. (2) O
  worker (CARD-009) e a entrega por SSE (ADR-0026) também precisam saber a etapa
  para emitir eventos, e nenhum dos dois passa por `api/schemas` — a regra seria
  reimplementada uma segunda vez **dentro do próprio servidor**, que é
  exatamente o defeito que o ADR-0016 §4 queria evitar, só que na fronteira
  errada. (3) A régua de cobertura mais frouxa (ADR-0019) cairia sobre a lógica
  mais cara de errar.

### Alternativa B — Função livre em `application` (ex.: `derive_stage(turn)`)

- **O que é:** um módulo de `application` com a função pura; borda e worker a
  chamam.
- **A favor:** resolve a reimplementação da Alternativa A sem pôr vocabulário de
  UI na entidade; e `application` também está sob a régua de 90%.
- **Por que foi rejeitada:** é uma função que só lê o estado de um agregado e
  não orquestra porta nenhuma — é comportamento de entidade escrito fora dela.
  Manteria a pergunta "existe trecho?" respondida por quem não é dono da
  coleção, e criaria o precedente de que regra sobre `Turn` pode morar em dois
  lugares. Anemia de domínio com um passo a mais de indireção.

### Alternativa C — Persistir a etapa numa coluna

- **O que é:** gravar `stage` em `turns`.
- **Por que foi rejeitada:** já rejeitada duas vezes (ADR-0016 Alternativa A,
  ADR-0023 Alternativa B) e nomeada como risco no CARD-018. Duas fontes para a
  mesma verdade. Listada aqui só para deixar registrado que a reabertura da
  questão do **lugar** não reabre a questão do **quê**.

## Consequências

**Positivas**

- A tabela de derivação do ADR-0023 é testável em milissegundos, sem FastAPI,
  sem container e sem rota — que é o que torna praticável o "teste obrigatório"
  que o ADR-0023 exige.
- Uma implementação só para **todos** os consumidores: `api/schemas` (CARD-010),
  o emissor de SSE (ADR-0026) e o worker (CARD-009). A Alternativa A daria uma
  para cada.
- A lógica cai sob a régua de 90% do ADR-0019 em vez da de 80% com folga.
- `delivered_partially` fica ao lado da invariante que ela descreve (`fail()` não
  apaga trecho), onde o leitor da entidade a encontra.

**Negativas — o preço aceito**

- **A entidade ganha vocabulário de apresentação.** `transcribing`/`thinking`/
  `speaking` são palavras da tela, e agora estão no núcleo. Se o produto renomear
  uma etapa por motivo de UI, o `domain` muda por motivo que não é de negócio.
  **Gatilho para reavaliar:** a primeira vez que dois clientes precisarem de
  etapas **diferentes** para o mesmo `Turn` — aí a projeção volta para a borda,
  e a entidade passa a expor só os artefatos.
- **`TurnStage` e `TurnStatus` são duas enums parecidas com um valor em comum
  (`completed`)**, no mesmo arquivo. É confusão previsível para quem chega, e o
  ADR-0008 continua exigindo que só a primeira possa crescer sem migration.
  Mitigado por docstring em cada uma, não por design.
- **O ADR-0016 §4 fica com uma frase morta**, e a skill
  `voicecoach-arquitetura` passa a contradizer o código até ser atualizada
  (dívida registrada no CARD-018 e no CARD-004). Regra de skill que não bate com
  o código é ADR novo — este — e nunca afrouxamento silencioso (ADR-0012).

**Equivalente mental .NET:** é a diferença entre calcular o `Stage` no
`ToDto()`/AutoMapper profile e tê-lo como `public TurnStage Stage => ...` no
próprio agregado, com o DTO fazendo `Stage = turn.Stage`. A escolha aqui é a
segunda, pela mesma razão de sempre: o mapeador não é dono da regra.
