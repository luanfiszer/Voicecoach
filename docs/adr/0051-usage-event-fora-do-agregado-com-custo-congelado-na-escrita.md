# ADR-0051 — `UsageEvent` fora do agregado, com o custo congelado na escrita

- **Status:** aceito
- **Data:** 2026-08-27
- **Complementa:** [ADR-0004](0004-persistencia-postgres-sqlalchemy-alembic.md),
  [ADR-0009](0009-estrategia-de-modelos-de-ia.md),
  [ADR-0010](0010-politica-de-custo-projeto-pessoal.md),
  [ADR-0013](0013-configuracao-tipada-fora-das-camadas.md),
  [ADR-0021](0021-prompt-caching-adiado-o-limiar-medido-nao-e-alcancado.md)
- **Critérios de obrigatoriedade** (`docs/adr/README.md`): **2** (fronteira de
  dados persistidos), **3** (afeta custo recorrente) e **5** (difícil de reverter
  depois que houver linhas gravadas)

## Contexto

O `TokenUsage` — as três contagens de entrada mais a saída — atravessava a porta
do professor desde o CARD-007 e era **descartado**: o `process_turn` lia
`feedback.feedback` e deixava `feedback.usage` cair no chão
(`grep -n usage process_turn.py` → zero ocorrências). Toda afirmação de custo do
projeto vinha de uma estimativa escrita em 2026-08-19 na §2 de
[`analise-custo-e-precificacao.md`](../analise-custo-e-precificacao.md).

Três forças tornaram este o momento:

1. **É pré-requisito do kill switch** (CARD-015), bloqueante de lançamento
   comercial. Quota sem registro de uso opera no escuro.
2. **O CARD-013 mudou o perfil de tokens e ninguém estava medindo.** O prompt v2
   é maior; a §2 supunha um system prompt de ~700 tokens, e o medido é ~1.488 de
   entrada **sem histórico nenhum**.
3. **O ADR-0021 adiou o prompt caching** porque o limiar do Haiku 4.5 (4.096
   tokens) não era alcançado — e deixou explícito, no item 3, que o `UsageEvent`
   registrando as três contagens separadas é o instrumento que detecta a mudança
   de regime. Sem ele, o gatilho de reabrir a decisão nunca dispara.

Três decisões deste card **não** estavam cobertas por ADR nenhum e foram
levadas ao desenvolvedor antes da primeira linha de código.

## Decisão

**Registrar o custo real de cada turn numa entidade `UsageEvent` própria, fora do
agregado `Turn`, com o custo em `Decimal` congelado no instante da escrita.**

### 1. O `UsageEvent` é gravado no mesmo commit do feedback, não no fechamento

O card dizia *"na mesma transação"*, e a frase já era falsa desde o CARD-009: o
docstring de `UnitOfWork` estabelece que **o turn não é uma transação, é uma
sequência de marcos confirmados**. A pergunta real era *em qual marco*.

O `UsageEvent` entra junto de `attach_reply`/`attach_corrections`, e a razão é
**"não perder o que já foi pago"** — deliberadamente diferente da razão do
CARD-013 para o mesmo lugar, que era "não apagar o que é do aluno". Um turn que
falhe depois disto, no `reply/full`, deixa registrado o custo de uma resposta que
o aluno viu falhar. Isso está **correto**: os tokens saíram da conta.

### 2. `UsageEvent` não é entidade filha do agregado `Turn`

Ele tem repositório próprio (`UsageEventRepository`) e **nenhum `relationship` em
`TurnRow`**. É o desenho oposto ao de `Correction`, entregue no dia anterior, e a
divergência é deliberada:

- ele é lido em **agregação** (`GROUP BY student_id`), nunca junto de um turn;
  carregá-lo em todo `TurnRepository.get()` seria peso no caminho crítico de
  1,8 s para um dado que aquela leitura não usa;
- `student_id` mora na linha **desnormalizado** — contraria o instinto, porque é
  derivável por `turns → sessions` —, e é isso que faz a agregação do CARD-015
  não precisar de join. Ela roda **dentro do `POST`**;
- ele responde a perguntas de outra natureza (custo, margem) e sobrevive a
  decisões de retenção próprias.

A chave primária é o **`turn_id`**, sem id surrogate: um turn tem um custo, e é a
PK que impõe isso. Uma segunda escrita vira `IntegrityError` → `ConflictingWriteError`,
em vez de duplicar silenciosamente toda soma daquele aluno.

### 3. O custo é congelado na escrita; preço desconhecido é `NULL`, nunca `0`

`estimated_cost_usd` é calculado uma vez, com a tabela de preços vigente, e
gravado. Consequência direta: **a tabela de preços é config descartável** — ela
responde "quanto custa hoje", nunca "quanto custava em julho". Quem responde a
segunda é a linha gravada.

A metade cara desta decisão é o modelo fora da tabela. Três saídas eram
possíveis, e duas são armadilhas:

| Saída | Por que não |
|---|---|
| gravar `0` | zero é o custo **verdadeiro** do STT e do TTS locais. O kill switch leria como grátis um turn que ninguém sabe precificar |
| levantar | derrubaria um turn cujo áudio o aluno **já ouviu**, por um problema que não é dele |
| **gravar `NULL` + log ERROR** | escolhida. Nulo significa "não sabemos precificar", as contagens de token ficam gravadas (a linha é reprecificável), e `StudentUsageTotals.unpriced_turns` torna a lacuna visível em vez de silenciosa |

É a frase do card — *"zero é dado, não ausência"* — aplicada ao outro lado.

### 4. Decorrências que não eram perguntas, mas viraram decisões

- **`TokenUsage` ganha `model`**, lido de `message.model` (o que **respondeu**) e
  não de `TEACHER_MODEL` (o que foi **pedido**). Contagem de token sem o modelo
  que a consumiu não tem preço, e o alias resolve para um id datado. A busca na
  tabela é por **prefixo mais longo**, o que dispensa uma linha nova a cada
  snapshot que o provedor publicar.
- **A tabela de preços mora em `config.py`** como constante de módulo tipada com
  o `LlmPrice` do domínio, protegida por `MappingProxyType`. Não é campo de
  `Settings`: um dicionário de `Decimal` por modelo não vem de variável de
  ambiente de forma honesta. `config.py` importar `domain` é a direção
  permitida — o contrato do import-linter proíbe a inversa (ADR-0013).
- **O caso de uso recebe uma função `Callable[[str], LlmPrice | None]`**, não a
  tabela: `application` não pode importar `config`. O gate foi verificado
  injetando o atalho — dois contratos quebraram, um deles pela cadeia indireta
  `config → pydantic`.
- **O volume de STT é `timedelta`**, não `stt_seconds: float`. O card pedia o
  segundo; um `float` de segundos ao lado do `timedelta` de `Turn.audio_duration`
  criaria a divergência de unidade que o CARD-015 teria de resolver.
- **`llm_model`, `stt_provider` e `tts_provider` são `VARCHAR`, não enum.** O
  conjunto não é fechado (o modelo é configuração — ADR-0009), e um tipo enum do
  Postgres exigiria migration a cada modelo novo. É o contraste explícito com
  `CorrectionType`, que é enum por ser fechado.
- **A agregação devolve minutos E turns.** A unidade da cota está listada como
  pendente de decisão de produto, com 3x de divergência medida (análise §8); uma
  agregação que trouxesse só uma responderia a pergunta antes de ela ser feita.

## Alternativas consideradas

### Alternativa A — `UsageEvent` como coleção filha do agregado `Turn`

- **O que é:** copiar inteiro o desenho fresco de `Correction` (ADR-0049) — PK
  composta, `selectinload` explícito, `cascade="all, delete-orphan"` — e ler o
  custo junto do turn.
- **Por que foi rejeitada:** o padrão de leitura é oposto. `Correction` é lida na
  tela de um turn; `UsageEvent` é lido somado por aluno e por dia. Um
  `relationship` novo em `TurnRow` entraria em **toda** leitura de turn, no
  caminho crítico de 1,8 s, sem responder a nenhuma pergunta daquela leitura — e
  esquecer o `selectinload` correspondente estouraria em runtime com
  `lazy="raise_on_sql"`. Amarraria também a retenção do custo à do turn, quando
  as duas perguntas têm ciclos diferentes.
- **Continua disponível** se o histórico do aluno passar a exibir custo por turn,
  o que hoje não é feature de produto nenhuma.

### Alternativa B — Recalcular o custo na leitura, a partir dos tokens gravados

- **O que é:** guardar só as contagens e derivar o custo na consulta, com a
  tabela de preços vigente.
- **Por que foi rejeitada:** transformaria a tabela de preços em **dado histórico
  eterno** — para responder "quanto gastei em julho" seria preciso saber qual
  preço valia em julho, ou seja, versionar a tabela para sempre e nunca poder
  apagar uma linha dela. E "quanto gastei em julho" mudaria de resposta a cada
  reajuste do provedor, que é a pior propriedade possível num número de custo.
- **O que se aceita perder:** um bug no cálculo fica gravado. Mitigação: as
  contagens de token estão todas na linha, então o recálculo retroativo é
  possível como operação deliberada — só não é o comportamento default.

### Alternativa C — Gravar o `UsageEvent` no `_fechar`, junto do `complete`

- **O que é:** só turn completo gera linha de custo.
- **Por que foi rejeitada:** perderia o custo de **todo** turn que falha depois do
  LLM — o custo mais fácil de perder de vista e o mais caro de não enxergar,
  porque é justamente o que acontece num incidente. O ganho seria uma tabela em
  que toda linha corresponde a um turn bem-sucedido, o que é conveniente e
  falso.

### Alternativa D — Não medir agora; seguir com a estimativa da análise §2

- **O que é:** manter o custo como projeção e construir o registro junto do
  CARD-015.
- **Por que foi rejeitada:** a estimativa já estava errada em 2026-08-26, quando o
  prompt v2 entrou, e ninguém soube. Sem instrumento, a próxima mudança de perfil
  também passa despercebida — e o CARD-015 precisaria decidir a unidade da cota
  sobre o mesmo número que este card acabou de corrigir.

## Consequências

**Positivas**

- O custo do produto deixa de ser estimativa. A §2 da análise foi conferida
  contra o medido e **errava em ~49% para cima** no turn sem histórico
  (US$ 0,004 estimado contra US$ 0,002678 medido), e errava também na
  **composição**: o "meio a meio" virou ~56% entrada / ~44% saída.
- O gatilho do ADR-0021 vira dado observável: as três contagens são gravadas com
  zero **como valor**, e a distância até o limiar de caching está registrada.
- `unpriced_turns` torna impossível confundir "custo baixo" com "custo que não
  soubemos calcular".
- O índice `(student_id, occurred_at)` já nasce na ordem certa para a consulta
  que o CARD-015 vai rodar dentro do `POST` — igualdade antes de faixa.

**Negativas — o preço aceito**

- **`student_id` duplicado na linha.** É dado derivável gravado, o que este
  projeto normalmente recusa (ADR-0016/0023). A exceção é consciente e tem um
  motivo que os outros casos não tinham: aqui o dado derivado está no caminho
  crítico de um request, e derivá-lo custa dois joins. Se a `Session` mudar de
  aluno — o que nenhuma regra hoje permite —, as linhas antigas ficam com o
  aluno antigo.
- **`stt_audio_duration` também é cópia** de `turns.audio_duration`, pela mesma
  razão e com o mesmo risco.
- **Uma tabela que cresce por turn, para sempre**, sem política de retenção
  definida. O CARD-017 trata mídia; custo não tem ciclo escrito. Fica como dívida
  nomeada.
- **O modelo fora da tabela de preços é uma falha silenciosa até alguém ler o
  log.** O ERROR existe, mas não há alerta — e não vai haver antes de haver
  observabilidade (Fase 3).
- **Nenhum backfill.** Todo turn processado antes desta migration é custo perdido
  para sempre. É o preço de o instrumento ter chegado depois do pipeline.

**Equivalente mental .NET:** é a diferença entre uma coluna calculada e uma
coluna gravada num relatório financeiro. A calculada é sempre coerente com a
regra de hoje; a gravada é sempre coerente com a regra **do dia em que o fato
aconteceu** — e num registro de custo é a segunda que se quer. O `decimal` do C#
é o paralelo exato do `Decimal` daqui, **com uma diferença que morde**: lá a
escala é do tipo, aqui ela vive num contexto global e mutável, e por isso todo
arredondamento neste módulo é explícito (`quantize`), nunca herdado.
