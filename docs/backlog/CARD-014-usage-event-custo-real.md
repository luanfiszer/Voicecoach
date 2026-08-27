# CARD-014 — UsageEvent: custo real por Turn (antecipado — é o instrumento de tudo)

- **ID:** CARD-014 · **Épico:** Fase 2 — Proteção de margem
- **Plataforma:** backend · **Esforço:** P · **Status:** ✅ concluído (2026-08-27)
- **Dependências:** CARD-009

## Contexto

Visão §D: *"a métrica de custo por usuário/sessão nasce no domínio"*. Com a
monetização confirmada (2026-08-19), este card deixa de ser higiene e vira
**instrumento de negócio**: é ele que diz se a margem existe.

## Por que agora

**Antecipado.** Três razões medidas:

1. **É pré-requisito do kill switch** (CARD-015), que é bloqueante de
   lançamento comercial — sem registro de uso, quota opera no escuro.
2. **100% do custo variável é o LLM** (~US$ 0,004/turn, meio a meio entre
   entrada e saída — análise de custo §2). O que não for medido aqui não é
   medido em lugar nenhum.
3. **É o detector de mudança de regime do prompt caching.** O ADR-0021 adiou o
   caching porque o limiar medido é 4.096 tokens e a conversa não chega lá — mas
   se o histórico crescer, ele passa a valer, e **nada avisa**. Registrar as três
   contagens de entrada é o que transforma isso em dado observável.

## Problema

Sem registro de uso real (tokens, duração de áudio, chars de TTS), quota, kill
switch e precificação seriam palpite.

## Proposta técnica

- Entidade/tabela `UsageEvent`: `turn_id, student_id, stt_seconds,
  llm_input_tokens, llm_output_tokens, tts_chars`, provider/modelo de cada
  passo, `estimated_cost_usd` (`Decimal`).
- **As três contagens de entrada, separadas** (ADR-0021):
  `llm_input_tokens`, `llm_cache_creation_tokens`, `llm_cache_read_tokens`.
  Hoje as duas últimas são sempre 0 — e é justamente por isso que precisam
  existir: o dia em que deixarem de ser é o gatilho de reabrir o caching. Escrita
  de cache custa **1,25×** e, com prefixo volátil, sai **~25% mais caro** que não
  usar cache (medição §5.3) — errar não é perder desconto, é pagar multa.
- **Contagem de turns por janela**, não só minutos: é o driver de custo real
  (análise de custo §8), e o CARD-015 precisa dela para decidir a unidade da cota.
- Tabela de preços por modelo em config, com data (ADR-0009).
- Gravado pelo use case ao completar o turn, **na mesma transação**.
- Query utilitária: custo por dia, por student e **por turn** — as três visões
  que a decisão de cota exige.

## Escopo

- **In:** entidade, tabela, cálculo, registro, query.
- **Out:** enforcement (CARD-015); entitlement por plano (CARD-023); dashboard.

## Critérios de aceite

- **Dado** um turn com Haiku (tokens conhecidos via mock), **então** o
  `UsageEvent` grava tokens e `estimated_cost_usd` bate com a tabela de preços
  (`Decimal`, teste exato).
- **Dado** STT/TTS locais, **então** o custo desses passos é 0 e os volumes
  (segundos, chars) ainda são gravados.
- **Dado** uma resposta sem cache, **então** as três contagens são gravadas com
  `cache_read = 0` — o valor 0 é dado, não ausência.
- **Dado** 3 turns de 2 students, **então** a agregação por student soma certo,
  em minutos **e** em turns.

## Riscos

Preços mudam — ficam em config com data. E `float` para dinheiro é o erro que
este card existe para não cometer.

## Objetivo de aprendizado

`Decimal` para dinheiro em Python (por que `float` quebra, `quantize`, contexto
— o paralelo do `decimal` do C#) e usage reporting dos SDKs de IA.


---

## Execução — 2026-08-27

Branch `card-014-usage-event-custo-real`. Decisão arquitetural em
[ADR-0051](../adr/0051-usage-event-fora-do-agregado-com-custo-congelado-na-escrita.md).

### O achado que mudou o plano

`grep -n "usage" src/voicecoach/application/use_cases/process_turn.py` devolvia
**zero ocorrências**: o `TokenUsage` atravessava a porta do professor desde o
CARD-007 e o caso de uso o descartava. A metade "coletar" do card já estava
pronta; o trabalho foi persistir, precificar e agregar.

### As três decisões levadas ao desenvolvedor antes da primeira linha

Nenhuma delas era coberta por ADR (regra do CLAUDE.md: decisão que os ADRs não
cobrem vai ao desenvolvedor **antes** do código).

| # | Pergunta | Resposta |
|---|---|---|
| D1 | Em que commit o `UsageEvent` é gravado? (o card dizia "na mesma transação", frase que o CARD-009 já tornou falsa) | **junto do `attach_reply`/`attach_corrections`** — "não perder o que já foi pago" |
| D2 | É coleção filha do agregado `Turn`, repositório próprio, ou os dois? | **repositório próprio**, sem `relationship` em `TurnRow` |
| D3 | O custo é congelado na escrita ou recalculado na leitura? | **congelado** — a tabela de preços vira config descartável |

### O que foi entregue

| Camada | Arquivo | O quê |
|---|---|---|
| domain | `domain/usage.py` (novo) | `UsageEvent`, `LlmPrice`, `estimate_llm_cost`, `StudentUsageTotals` |
| application | `ports/repositories.py` | porta `UsageEventRepository` (`add`, `get`, `totals_for_student`) — **sem `update`**: medição não se corrige |
| application | `ports/teacher_llm.py` | `TokenUsage` ganha `model` (o que **respondeu**, não o que foi pedido) |
| application | `use_cases/process_turn.py` | `_registrar_uso`, `_Cascata` com `tts_chars` somado onde as sentenças passam |
| adapters | `llm/anthropic_teacher.py` | `_uso` lê `message.model`; `_FinalMessage` ganha a propriedade |
| adapters | `persistence/{models,mappers,repositories}.py` | `UsageEventRow`, mappers, `SqlAlchemyUsageEventRepository` com agregação por `func.sum`/`func.count` |
| config | `config.py` | `LLM_PRICES` (tabela com data, `MappingProxyType`) e `preco_do_modelo` (busca por prefixo mais longo) |
| worker | `worker/main.py` | injeta o repositório, `preco_do_modelo` e o provider **resolvido** do STT |
| migration | `c5e2a71b93d4_usage_events_o_custo_vira_linha.py` | à mão, sem enum, com o índice `(student_id, occurred_at)` |

**Dependências novas: nenhuma.** `Decimal`, `date` e `MappingProxyType` são
stdlib; `Numeric`/`Interval` já vinham do SQLAlchemy. Logo, nenhuma alteração nas
listas `forbidden` do `pyproject.toml`.

### Critérios de aceite — evidência

**1. Custo exato com `Decimal` e tokens conhecidos.** Igualdade, não aproximação:

```
uv run pytest tests/domain/test_usage.py -q
12 passed in 0.01s
```

1084 tokens de entrada a US$ 1/MTok + 180 de saída a US$ 5/MTok =
`Decimal("0.00198400")`, conferido contra a `LLM_PRICES` real (não um preço
inventado no teste). O mesmo número é afirmado do outro lado, no caso de uso
(`test_o_custo_do_turn_e_gravado_e_bate_exato_com_a_tabela_de_precos`) e depois
de ida e volta ao Postgres (`test_roundtrip_do_usage_event_preserva_decimal_e_intervalo`).

`test_um_turn_arredondado_a_dois_digitos_seria_zero` demonstra por que a escala
é 8: `round(custo, 2) == Decimal("0.00")`.

**2. As três contagens de entrada gravadas, com `cache_read = 0` como valor.**
Afirmado em memória (`test_as_tres_contagens_de_entrada_sao_gravadas_e_o_zero_e_um_valor`)
e contra Postgres (`test_as_tres_contagens_de_entrada_voltam_do_banco_como_zero`).
As colunas são `NOT NULL` — nulo aqui seria "não medimos", que nunca é verdade.

**3. STT e TTS com custo 0 e volume registrado.** `stt_audio_duration` vem de
`turn.audio_duration` (`timedelta`, sem unidade nova ao lado), `tts_chars` é a
soma de `len(texto)` das sentenças, contada dentro do `_cascata`. Verificado em
`test_stt_e_tts_tem_volume_gravado_e_custo_zero`.

**4. Agregação por student, em minutos E em turns**, contra Postgres real com
3 turns de 2 students:

```
uv run pytest tests/adapters/test_persistence.py -q
32 passed in 2.94s
```

O esquema real, lido do banco de desenvolvimento depois do `alembic upgrade head`:

```
                              Table "public.usage_events"
          Column           |           Type           | Nullable
---------------------------+--------------------------+----------
 turn_id                   | uuid                     | not null
 student_id                | uuid                     | not null
 occurred_at               | timestamp with time zone | not null
 llm_model                 | character varying(120)   | not null
 llm_input_tokens          | integer                  | not null
 llm_cache_creation_tokens | integer                  | not null
 llm_cache_read_tokens     | integer                  | not null
 llm_output_tokens         | integer                  | not null
 stt_audio_duration        | interval                 | not null
 stt_provider              | character varying(40)    | not null
 tts_chars                 | integer                  | not null
 tts_provider              | character varying(40)    | not null
 estimated_cost_usd        | numeric(12,8)            |
Indexes:
    "usage_events_pkey" PRIMARY KEY, btree (turn_id)
    "ix_usage_events_student_occurred" btree (student_id, occurred_at)
```

`downgrade -1` seguido de `upgrade head` roda limpo — nenhum tipo órfão, que é o
contraste com a migration do CARD-013 (lá os dois enums precisavam de `DROP TYPE`
à mão, e esquecer fazia a próxima subida falhar).

**5. A §2 da análise de custo conferida contra o número real e atualizada.** Ela
errava em quatro pontos, e o quanto está escrito lá:

| A estimativa dizia | O medido diz | Erro |
|---|---|---|
| system prompt ~700 tokens | prefixo sem histórico = **1.488** | **2,1x para baixo** |
| ~US$ 0,004/turn | **US$ 0,002678** | **~49% para cima** |
| "meio a meio" entrada/saída | **56% / 44%** | a composição inverteu |
| saída ~400 tokens | **238** | 1,7x para cima |

A projeção era **pessimista**, não otimista — nada aqui piora a margem. Mas a
alavanca mudou de lado: com o v2 a **entrada** virou a metade maior, e entrada é
o que o caching atacaria.

**6. A distância até o limiar de caching do ADR-0021, registrada.**

| Cenário | Entrada | % do limiar (4.096) |
|---|---|---|
| v1 sem histórico (base do ADR-0021) | 1.242 | 30% |
| **v2 sem histórico (medido)** | **1.488** | **36%** |
| v2 + 6 turns de histórico (derivado, não medido) | ~2.400 | ~58% |

O gatilho continua não atingido — e agora isso é **dado gravado**, não memória.

### Quality gates

```
uv run ruff format --check src tests   → 111 files already formatted
uv run ruff check src tests            → All checks passed!
uv run mypy                            → Success: no issues found in 109 source files
uv run lint-imports                    → Contracts: 4 kept, 0 broken.
uv run pytest --cov --cov-fail-under=80 → 332 passed, 9 deselected · 93.07%
coverage do núcleo (domain+application) → 99% (limiar 90%)
```

`domain/usage.py`: **100%** de cobertura.

**O gate morde — provado, não afirmado.** Injetei o atalho exato que este card
torna tentador (o caso de uso importando `LLM_PRICES` direto de `config`):

```
Contracts: 2 kept, 2 broken.
  application não conhece framework nem SDK de provider  BROKEN
  configuração é composição: domain e application não leem config  BROKEN

voicecoach.application is not allowed to import pydantic:
-   voicecoach.application.use_cases.process_turn -> voicecoach.config (l.73)
    voicecoach.config -> pydantic (l.23)
```

Note o **segundo** contrato: ele quebrou pela **cadeia indireta**
`process_turn → config → pydantic`, sem ninguém ter escrito `import pydantic`. É
a lição da Q12 (CARD-009) aparecendo sozinha. Revertido: 4 kept, 0 broken.

**O `mypy` cobrou os fakes de novo, na hora.** No instante em que `TokenUsage`
ganhou `model`, com o `pytest` ainda verde:

```
tests/adapters/test_anthropic_teacher.py:48: error: Argument 1 to "AnthropicTeacher"
  has incompatible type "FakeClient"; expected "_Client"
  note: messages: expected "_Messages", got "FakeMessages"
```

É a sétima demonstração do mecanismo da Q7 neste repositório.

### Item de ADR da DoD — conferido contra critério escrito

Conferido contra a lista "Quando um ADR é OBRIGATÓRIO" de `docs/adr/README.md`.
Aplicaram-se **três** critérios, e o ADR-0051 os cita:

- **critério 2** (define ou altera uma fronteira — formato de dados
  persistidos): tabela nova, e a decisão D2 sobre não ser filha do agregado;
- **critério 3** (afeta custo recorrente): é o tema do card, e a decisão D3
  (congelar vs. recalcular) é dele;
- **critério 5** (difícil de reverter): a decisão D1 sobre o momento da escrita
  fica cara de mudar depois que houver linhas gravadas.

### Regra do explicador

**Q15, reapresentada na abertura** (a única que volta, pela regra nova do
LEARNING-0005): *"num `@dataclass(frozen=True, slots=True)`, o que acontece se um
campo for `list[...]` em vez de `tuple[...]`?"*

- **Desfecho: dispensada pelo desenvolvedor** ("Não sei / dispensada"). Registrada
  como tal — nunca como cumprida nem como parcial. **Arquivada** com a evidência,
  pela regra nova.
- A decisão que ela tocava foi tomada mesmo assim, e está escrita no docstring de
  `UsageEvent`: **nenhum campo é coleção**. Um `list` num registro de medição
  seria a pior versão do problema — mutável por dentro, `mypy --strict` verde, e
  o teste de roundtrip comparando iguais dois eventos que divergiram.

**As três decisões do ponto da decisão (D1, D2, D3) foram feitas ANTES da
primeira linha de código e todas respondidas pelo desenvolvedor.** Item da DoD:
**verde** — o item é sobre as perguntas desta sessão (CLAUDE.md, regra 4 do
explicador).

### Custo desta sessão

**US$ 0,00.** Nenhuma chamada real ao provedor: o card inteiro é testável com os
tokens conhecidos que o fake já trazia desde o CARD-007
(`input_tokens=1084, output_tokens=180`), e o perfil do v2 saiu do benchmark que
o CARD-013 já tinha gravado.

### Dívidas explícitas

| O que ficou | Gatilho / card que resolve |
|---|---|
| **A linha "v2 + histórico" da §2 é derivada, não medida** (usa o "~150 tok/troca" do ADR-0021) | ~3 execuções reais (~US$ 0,01), quando o desenvolvedor autorizar |
| **`usage_events` cresce por turn, sem política de retenção** | o CARD-017 trata mídia; custo não tem ciclo escrito |
| **Modelo fora da tabela de preços só aparece no log** (ERROR, sem alerta) | observabilidade da Fase 3 |
| **`student_id` e `stt_audio_duration` são cópia** de dado derivável | aceito no ADR-0051 com o motivo (caminho crítico de um request); revisar se `Session` puder trocar de aluno |
| **Nenhum backfill** — todo turn anterior a esta migration é custo perdido | não há conserto: o instrumento chegou depois do pipeline |
| **Processos velhos de pé na máquina** (uvicorn e worker de 07:52, código antigo) | não foram subidos por esta sessão; derrubar antes de qualquer medição ponta a ponta |
