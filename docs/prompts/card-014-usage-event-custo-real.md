# Prompt — CARD-014: o custo deixa de ser estimativa e vira linha no banco

- **Tipo:** prompt de sessão, complemento de `/executa-card 014`
- **Escrito em:** 2026-08-26, no fechamento do CARD-013 (PR #18)
- **Status:** ✅ executado em 2026-08-27 (PR #20) — ver a seção *Execução* do
  [CARD-014](../backlog/CARD-014-usage-event-custo-real.md) e o
  [ADR-0051](../adr/0051-usage-event-fora-do-agregado-com-custo-congelado-na-escrita.md)

> **Este prompt não substitui o `/executa-card`.** Aquele comando carrega o
> protocolo (branch, ordem de leitura, premissas antes do plano, DoD item a
> item, convenção de commit). **Rode `/executa-card 014` e leia isto junto** —
> aqui está o que é específico deste card, a arqueologia já feita, **o que o
> card assume e acabou de mudar** (§3.2), e as armadilhas que custam um card
> inteiro se descobertas tarde.

---

## 0. Antes do plano: a regra é nova, e a fila tem exatamente uma linha

**A regra do explicador mudou no CARD-013** ([LEARNING-0005](../learnings/0005-a-fila-de-perguntas-nao-fecha-e-a-metade-nova-da-regra-ja-funciona.md)),
por decisão do desenvolvedor. O que isso muda para esta sessão, na prática:

- o item da DoD é sobre **as perguntas desta sessão**, não sobre passivo antigo;
- `docs/perguntas-em-aberto.md` é **arquivo**, não cobrança — as 11 antigas estão
  registradas ao lado do que a execução demonstrou sobre cada uma, e **não**
  voltam;
- volta **uma** pergunta: a da sessão imediatamente anterior que ficou sem
  desfecho.

Essa pergunta é a **Q15**, e ela é para reapresentar na abertura, antes do plano:

| # | Pergunta | Por que ficou aberta |
|---|---|---|
| **Q15** | Num `@dataclass(frozen=True, slots=True)`, o que acontece se um campo for `list[...]` em vez de `tuple[...]`? | Foi a reformulação da 1ª pergunta do CARD-013. Resposta dada: *"mypy vermelho na hora"* — **errada**. A execução mostrou: `frozen=True` congela a ligação e não o objeto (`append` funcionou), `mypy --strict` deu `Success`, e só o `hash()` estourou `TypeError: unhashable type: 'list'`. A reformulação que a regra permite já tinha sido gasta |

> **Ela toca este card de verdade**, e não por paralelo: `UsageEvent` é a
> próxima entidade nova, vai ser comparada por valor em teste de roundtrip
> exatamente como `Correction` foi, e a escolha `tuple` vs. `list` reaparece se
> ele carregar qualquer coleção. **Se a resposta vier, o item fecha; se não
> vier, ela é arquivada com a evidência** — não fica pendurada. É a regra nova
> funcionando.

**Sem reapresentação da fila antiga.** Se você se pegar listando Q7/Q9/Q11, pare:
elas foram arquivadas em 2026-08-26 e reabrem só quando um card tocar a decisão
delas, refeitas no ponto da decisão daquele card.

---

## 1. Por que este é o próximo card

O card já se explica ("é o instrumento de tudo"), mas há uma razão nova, de
ontem, que o texto dele não tem:

**O CARD-013 mudou o perfil de tokens e ninguém está medindo.** O prompt v2 é
bem maior que o v1, e a medição registrada em
[`analise-custo-e-precificacao.md` §2](../analise-custo-e-precificacao.md)
assume um system prompt de **~700 tokens**. O número real medido no CARD-013 é
**~1.490 tokens de entrada sem histórico nenhum** (`benchmarks/results/llm_prompt_v1_vs_v2.json`).
Ou seja: a base de toda projeção de margem — inclusive a tabela de múltiplos que
tornou o CARD-015 bloqueante — está **desatualizada desde ontem**, e o único
jeito de saber por quanto é medir o real, que é o que este card constrói.

E há a consequência de segunda ordem, que é o item 3 da seção "Por que agora" do
próprio card:

- o ADR-0021 adiou o prompt caching porque o limiar do Haiku 4.5 é **4.096
  tokens** e a conversa não chegava lá;
- com o v2, a entrada é ~1.5k **sem** histórico, e ~2.8k com o histórico de 10
  turns que o `history_turns` já monta;
- **isso é 68% do limiar, não 25%.** A "mudança de regime" que o CARD-014 existe
  para detectar deixou de ser hipotética entre ontem e hoje.

## 2. O que já está decidido e não se rediscute

- [**ADR-0010**](../adr/0010-politica-de-custo-projeto-pessoal.md) — **teto
  duplo**: console do provedor **e** aplicação. Este card constrói o insumo do
  segundo; o *enforcement* é o CARD-015.
- [**ADR-0021**](../adr/0021-prompt-caching-adiado-o-limiar-medido-nao-e-alcancado.md)
  — **as três contagens de entrada, separadas**. Hoje `cache_creation` e
  `cache_read` são 0 em toda chamada, e **é por isso que precisam existir**:
  zero é dado, não ausência. Escrita de cache custa **1,25×**, e com prefixo
  volátil sai ~25% **mais caro** que não cachear — errar não é perder desconto,
  é pagar multa.
- [**ADR-0013**](../adr/0013-configuracao-tipada-fora-das-camadas.md) —
  **`Decimal` para dinheiro, nunca `float`**, e configuração tipada fora das
  camadas. `Settings` já tem `daily_budget_usd`/`monthly_budget_usd` em
  `Decimal`: siga o precedente, não invente outro.
- [**ADR-0009**](../adr/0009-estrategia-de-modelos-de-ia.md) — modelo por
  config. A **tabela de preços com data** é consequência direta disso.
- [**ADR-0004**](../adr/0004-persistencia-postgres-sqlalchemy-alembic.md) +
  [**ADR-0012**](../adr/0012-regra-de-camada-como-contrato-executavel.md) —
  entidade no `domain`, tabela e mapper em `adapters/persistence`, porta em
  `application/ports`. A skill `voicecoach-arquitetura` é de consulta
  obrigatória.
- [**ADR-0049**](../adr/0049-correction-e-entidade-persistida-e-os-campos-texto-viram-derivacao.md)
  — o precedente **fresco** de entidade filha persistida: `Correction` foi
  entregue ontem com PK composta, enum com `values_callable`, `selectinload`
  explícito e roundtrip contra Postgres real. **Copie esse desenho**, não invente
  outro — e note onde ele **não** se aplica (§4.2).

## 3. Arqueologia — verificada no repositório em 2026-08-26

### 3.1 O achado que muda o plano: **o `usage` já chega e é jogado fora**

`TeacherLlm` devolve `FeedbackReady(feedback=..., usage=TokenUsage(...))`, com as
quatro contagens já preenchidas pelo adapter (`_uso`, em
`adapters/llm/anthropic_teacher.py`). O `process_turn` recebe esse objeto,
**usa `feedback.feedback` e descarta `feedback.usage`**:

```python
# process_turn.py, ~linha 262 — repare no que NÃO acontece com `feedback.usage`
turn.attach_reply(feedback.feedback.spoken_reply, self._clock())
turn.attach_corrections(feedback.feedback.corrections)
```

`grep -n "usage" src/voicecoach/application/use_cases/process_turn.py` → **zero
ocorrências**. O dado mais caro do produto atravessa a porta e cai no chão.

**Consequência para o plano:** a metade "coletar" do card **já está pronta** desde
o CARD-007, com o ADR-0021 explicando por que os campos existem separados. O
trabalho é persistir, precificar e agregar — não instrumentar o adapter.

### 3.2 O que o card assume e **mudou desde que ele foi escrito**

| O card diz | A realidade em 2026-08-26 |
|---|---|
| *"`tts_chars`"* | O TTS é **local** (Piper, ADR-0032) e a porta recebe **texto por sentença**. `tts_chars` é `sum(len(texto))` das sentenças — dado de volume, custo 0. Não existe contador de chars em lugar nenhum ainda: você vai ter que somá-lo no `_cascata`, onde as sentenças passam |
| *"`stt_seconds`"* | **Já existe e não precisa ser medido**: é `turn.audio_duration` (um `timedelta`, insumo declarado da quota). Não crie um campo novo com outra unidade ao lado dele — crie a divergência que o CARD-015 vai ter que resolver |
| *"Entidade/tabela `UsageEvent`… `llm_input_tokens, llm_output_tokens`"* | Os nomes do card **não** incluem as três contagens separadas; a seção seguinte do próprio card **inclui**. Vale a pena as duas listas serem a mesma antes de escrever a migration |
| *"custo ~US$ 0,004/turn, meio a meio"* | Base do v1. **O v2 mudou a proporção**: entrada cresceu ~20%, saída caiu ~8,5% (medição do CARD-013). O "meio a meio" provavelmente virou ~70/30 — e este card é quem vai dizer o número certo, em vez de reestimar |

### 3.3 O que copiar do CARD-013, literalmente

- **Enum indo para o banco:** `StrEnum` + `Enum(..., values_callable=...)` no
  modelo. Sem isso o Postgres guarda `HAIKU` e o JSON trafega `haiku`.
- **Roundtrip contra Postgres real** (ADR-0018), comparando a entidade inteira
  com um `==` só — funciona porque `frozen=True` dá `__eq__` por valor. É a Q15
  em forma de teste.
- **`selectinload` explícito** se houver relacionamento: no SQLAlchemy async não
  existe lazy loading, e `lazy="raise_on_sql"` transforma o esquecimento em
  `InvalidRequestError` na hora, não em N+1 silencioso.
- **A migration escrita à mão**, não por autogenerate: o `ondelete` da FK não sai
  do `cascade` do ORM. E **cuidado com o enum**: no CARD-013, chamar `.create()`
  antes do `create_table` custou uma execução —
  `DuplicateObjectError: type "correction_type" already exists`. Quem cria é o
  `create_table`; quem remove, no `downgrade`, é você.

## 4. As armadilhas — o que o texto do card não antecipa

### 4.1 "Na mesma transação" é uma frase que o CARD-009 já tornou falsa

O card diz: *"gravado pelo use case ao completar o turn, **na mesma
transação**"*. **Não existe "a" transação de um turn.** O docstring de
`UnitOfWork` é explícito e vale a pena ler antes de planejar:

> *"o turn não é uma transação: é uma sequência de marcos confirmados"*

O `_gravar` faz `turns.update()` + `uow.commit()` a cada marco, de propósito —
uma transação única deixaria os trechos invisíveis exatamente durante os ~2 s em
que o aluno pode reconectar (ADR-0026 item 3).

**A pergunta que o plano tem de responder:** o `UsageEvent` é gravado no
**mesmo commit** de qual marco? Candidatos, com o trade-off honesto:

- junto do `attach_reply`/`attach_corrections` (é onde o `usage` chega, e é a
  escrita que o CARD-013 já usou pela mesma lógica) — **mas** aí um turn que
  falhe no `_fechar` registra custo de um turn que o aluno viu falhar. O que
  está **certo**: os tokens foram pagos;
- no `_fechar` — custo só de turn completo, e **perde-se o custo de todo turn
  que falhou depois do LLM**, que é justamente o custo que ninguém quer perder
  de vista.

Note que a resposta aqui **é diferente** da do CARD-013 na justificativa, ainda
que provavelmente igual no lugar: lá o argumento era "não apagar o que é do
aluno"; aqui é "não perder o que já foi pago".

### 4.2 Onde o desenho do CARD-013 **não** se aplica: `UsageEvent` não é filho do `Turn`

`Correction` é entidade filha do agregado `Turn` — carregada junto, PK composta,
`cascade="all, delete-orphan"`. É tentador copiar isso inteiro. **Não copie sem
decidir**, porque `UsageEvent` responde a perguntas de outra natureza:

- ele é lido em **agregação** ("custo por student por dia"), não em leitura de
  turn. Carregá-lo junto de todo `TurnRepository.get()` é peso puro no caminho
  crítico de 1,8 s;
- ele precisa sobreviver a decisões de retenção **diferentes** das do turn: o
  CARD-017 apaga áudio, e o custo de um turn cujo áudio expirou continua sendo
  custo;
- `turn_id` **e** `student_id` na mesma linha é desnormalização deliberada — é o
  que faz `GROUP BY student_id` não precisar de join. Vale a pena, e vale a pena
  estar escrito **por que** vale, porque contraria o instinto.

**Decida explicitamente** se ele é coleção do agregado, repositório próprio, ou
os dois. E cuidado com o inverso do CARD-013: um `relationship` novo em `TurnRow`
sem `selectinload` **estoura em runtime**.

### 4.3 O preço tem data, e a tabela tem uma pergunta escondida

*"Tabela de preços por modelo em config, com data (ADR-0009)"* — a parte fácil.
A escondida é: **o `estimated_cost_usd` é congelado no momento da escrita, ou
recalculado na leitura?**

- congelado: a linha continua verdadeira quando o preço mudar, mas um bug no
  cálculo fica gravado para sempre;
- recalculado: corrige retroativamente, mas exige que a tabela de preços
  histórica exista para sempre, e "quanto gastei em julho" muda de resposta
  quando o provedor reajusta.

O nome do campo (`estimated_cost_usd`) sugere a primeira. **Escreva a decisão**,
porque ela determina se a tabela de preços é config descartável ou dado.

E o detalhe de `Decimal` que morde: preço é **por milhão de tokens**
(US$ 1/MTok). `tokens * preco / 1_000_000` em `Decimal` dá muitas casas
decimais — decidir **onde** e **com que arredondamento** aplicar `quantize` é
parte do teste "bate exato com a tabela de preços", e fazê-lo cedo demais perde
precisão em turns baratos (US$ 0,004 arredondado a 2 casas é **zero**).

### 4.4 Uma agregação sem índice é uma query que fica lenta em silêncio

O critério de aceite pede agregação por student e por dia. `GROUP BY student_id`
com `WHERE created_at BETWEEN ...` sobre uma tabela que cresce por turn quer um
índice composto — e o CARD-015 vai chamar essa query **no caminho do POST**, para
decidir se o aluno ainda tem cota. **É a única query deste card que vai para o
caminho crítico de um request**, e é o tipo de coisa que não aparece com 10
linhas em desenvolvimento.

### 4.5 O teste "bate exato" precisa de tokens conhecidos, e o mock certo já existe

O critério de aceite diz *"tokens conhecidos via mock"*. `tests/adapters/fakes_llm.py`
já tem `FakeUsage` e `FEEDBACK_COMPLETO`, e `tests/application/test_process_turn.py`
já tem uma `USAGE` fixa com `input_tokens=1084, output_tokens=180`. **Use essas
constantes**: o teste de custo exato fica sendo aritmética verificável à mão, e
não mais um fake novo.

## 5. Escopo — o que corta se estourar

- **Não corte:** as **três** contagens de entrada separadas (é o item 3 da razão
  de o card existir), `Decimal`, a tabela de preços com data, e a agregação por
  **turns** além de minutos — sem ela o CARD-015 não consegue decidir a unidade
  da cota.
- **Pode virar card próprio:** dashboard (já está em "Out"), enforcement
  (CARD-015), entitlement por plano (CARD-023).
- **Se descobrir que a §2 da análise de custo ficou errada:** atualize-a com o
  número medido e diga por quanto errava. Foi assim que o ADR-0021 nasceu, e é o
  precedente que o CARD-013 seguiu ao escrever os +74 ms que ninguém queria ver.

## 6. Governança

1. **Item de ADR da DoD** — confira contra `docs/adr/README.md` e **cite o
   critério** (LEARNING-0003). Candidatos já visíveis:
   - **critério 2** — `UsageEvent` no domínio + tabela: fronteira de dados
     persistidos (e a decisão de §4.2 sobre agregado);
   - **critério 3** — *afeta custo recorrente*: é literalmente o tema do card, e
     a decisão de congelar vs. recalcular o preço (§4.3) é dele;
   - **critério 5** — a decisão do momento da escrita (§4.1) é cara de reverter
     depois que houver linhas gravadas.
2. **A skill `voicecoach-arquitetura` é de consulta obrigatória** (card de
   backend). Regra que não bater com o código é ADR novo ou bug — nunca
   afrouxamento em silêncio.
3. **Decisão que os ADRs não cobrem vai ao desenvolvedor ANTES da primeira linha
   de código.** Nesta sessão são pelo menos três: o momento da escrita (§4.1), se
   `UsageEvent` é filho do agregado (§4.2), e congelar vs. recalcular o custo
   (§4.3).

## 7. Definition of Done específica deste card

Além da DoD do `CLAUDE.md`:

- [ ] **Custo exato**, provado com `Decimal` e tokens conhecidos do fake que já
      existe — teste de igualdade, não de aproximação.
- [ ] **As três contagens de entrada gravadas**, com `cache_read = 0` **como
      valor**, e um teste que afirma isso (zero é dado, não ausência).
- [ ] **STT e TTS com custo 0 e volume registrado** — `stt_seconds` vindo de
      `turn.audio_duration`, `tts_chars` somado das sentenças.
- [ ] **Agregação por student, em minutos E em turns**, provada contra Postgres
      real (ADR-0018) com 3 turns de 2 students.
- [ ] **A §2 da análise de custo conferida contra o número real** do v2 e
      atualizada, com o quanto ela errava escrito.
- [ ] **A distância até o limiar de caching do ADR-0021 registrada** com o
      número medido: é o gatilho que este card existe para tornar observável.
- [ ] Q15 reapresentada na abertura, com desfecho registrado (respondida /
      dispensada / arquivada com a evidência).
- [ ] Card atualizado e `docs/backlog/README.md` atualizado.

## 8. Restrições

- **Branch própria** a partir de `main` (com o CARD-013 mergeado — PR #18).
  `main` é protegida. **Confira `git branch --show-current` depois de criar a
  branch**: no CARD-011 dois commits caíram em `main` apesar de o `git switch -c`
  ter reportado sucesso.
- Commit **nunca** leva trailer `Co-Authored-By`
  ([LEARNING-0001](../learnings/0001-commit-com-coautoria-indesejada-do-agente.md)).
- **Não pushe nem abra PR sem perguntar.**
- **Custo:** este card é quase todo testável com fakes — tokens conhecidos, custo
  aritmético. **Não precisa de execução real do pipeline para os critérios de
  aceite.** Se rodar o pipeline real para conferir o perfil de tokens do v2,
  bastam ~3 execuções (~US$ 0,01). Declare o total no card (ADR-0010).
- **Migration nova sobe no banco de desenvolvimento**: o CARD-013 aplicou a
  `a3f1c8b52e94` lá. Rode `uv run alembic upgrade head` antes de testar à mão.

### Como subir o ambiente inteiro (conferido no CARD-013)

```bash
docker compose up -d
cd backend && uv run alembic upgrade head
(cd backend && uv run uvicorn voicecoach.api.app:create_app --factory --host 0.0.0.0 --port 8000 &)
(cd backend && uv run voicecoach-worker &)
```

> **Cuidado com processos velhos:** aconteceu no CARD-012 **e de novo no
> CARD-013** — uma API de horas antes ficou de pé servindo código antigo.
> `ps aux | grep -E "uvicorn|voicecoach-worker"` antes de medir qualquer coisa,
> e derrube o que você subiu ao terminar.

### Uma prova ponta a ponta barata, se quiser uma

O CARD-013 provou o pipeline inteiro sintetizando o áudio de entrada com o
**próprio TTS local** (custo zero) e mandando pelo `POST`:

```python
audio = await create_text_to_speech(get_settings()).synthesize("Yesterday I go to store.")
# grava WAV → curl -F "audio=@erro.wav;type=audio/wav" .../turns
```

É mais barato e mais reprodutível que gravar pelo microfone, e o insumo fica
igual entre execuções.

- Responda em português. O desenvolvedor é **sênior em C#/.NET** e **iniciante
  em Python**: nada de explicar DDD, repositório ou camadas; **sempre** explicar
  qual biblioteca Python resolve o quê e por que ela, e **parar para explicar em
  3 linhas** qualquer idioma sem paralelo em C# — neste card, provavelmente: o
  contexto e o `quantize` do `decimal` (que **não** é o `decimal` do C#: aqui a
  precisão é global e mutável), `Numeric`/`NUMERIC` do SQLAlchemy indo e voltando
  como `Decimal`, e agregação com `func.sum` sem carregar entidade.
