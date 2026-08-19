# CARD-018 — Turn com trechos de áudio: domínio, invariantes e migration

- **ID:** CARD-018 · **Épico:** Fase 1 — Fatia vertical em cascata
- **Plataforma:** backend · **Esforço:** P · **Status:** **concluído** (2026-08-19)
- **Dependências:** CARD-005 (concluído), ADR-0023

## Contexto

O CARD-005 modelou o `Turn` sob o ADR-0016: cada artefato é **um** objeto,
produzido inteiro. O [ADR-0023](../adr/0023-ciclo-de-vida-do-turn-com-entrega-em-cascata.md)
substituiu essa premissa — com a cascata, o áudio da resposta é uma sequência
ordenada de trechos, e o primeiro deles existe **antes** de `reply_text` estar
completo.

O CARD-005 está concluído e não se reabre. Este card é o delta.

## Por que agora

É o primeiro card do caminho crítico: sem a entidade de trecho, o CARD-008 não
tem onde gravar a frase sintetizada e o CARD-009 não tem como emitir nada antes
do fim. Todo o alvo de 1,8 s passa por aqui, e este é o momento mais barato de
pagar — **não existe nenhum turn em banco para migrar**.

## Problema

Hoje `Turn` tem `audio_ref` singular e a etapa derivada usa `reply_text` como
condição de `speaking`. Com a cascata, essa tabela de derivação passa a mentir:
haverá áudio tocando com `reply_text` ainda nulo.

## Proposta técnica

- Entidade `TurnAudioChunk` no domínio: `index` (0-based, denso),
  `storage_key`, `duration_seconds`, `text`, `created_at`. Relacionamento
  `Turn` 1-N, ordenado por `index`.
- `Turn.append_audio_chunk(...)` como único caminho de escrita, com as
  invariantes do ADR-0023: índice denso e crescente; proibido acrescentar em
  turn `completed` ou `failed`.
- `Turn.complete(now)` **já** exige `reply_audio_ref` não-nulo
  (`domain/turn.py`) — essa invariante nasce pronta e passa a significar "o
  áudio inteiro concatenado existe". Nada a mudar aqui.
- `Turn.fail(reason)` continua válido a partir de `processing` **com trechos
  presentes**, e **não apaga trecho nenhum** (o aluno ouviu; o registro tem de
  dizer isso).
- Propriedades derivadas, não colunas: `stage` (nova tabela do ADR-0023) e
  `delivered_partially`.
- Migration Alembic: tabela `turn_audio_chunks` com unique `(turn_id, index)`.
  **`turns` não muda** — `reply_audio_ref` já tem o nome certo e já significa o
  áudio inteiro. O delta é só a tabela filha.
- `TurnRow` ganha o `relationship` ordenado; `turn_from_row`/`turn_to_row`/
  `apply_turn` (`adapters/persistence/mappers.py`) passam a mapear a coleção, e
  `SqlAlchemyTurnRepository.get` carrega com `selectinload` — no async não
  existe lazy loading de graça.

## Escopo

- **In:** domínio, invariantes, migration, testes de domínio.
- **Out:** gravar de fato os trechos (CARD-008); emitir eventos (CARD-010);
  schema de API (CARD-010).

## Critérios de aceite

- **Dado** um `Turn` em `processing` sem artefato, **então** `stage` é
  `transcribing`; com `transcript`, `thinking`; com 1 trecho, `speaking`; com
  `reply_audio_ref`, `completed`.
- **Dado** um `Turn` com 2 trechos, **quando** `fail("tts timeout")`, **então**
  o status é `failed`, os 2 trechos permanecem e `delivered_partially` é `True`.
- **Dado** um `Turn` `completed`, **quando** se tenta acrescentar trecho,
  **então** levanta `DomainError` (ADR-0017).
- **Dado** um índice repetido ou furado, **então** a operação falha — no domínio
  e no banco (constraint testada).
- Cobertura de `domain` permanece ≥ 90% (ADR-0019).

## Riscos

Tentação de persistir `stage` como coluna "para facilitar a query operacional" —
é exatamente o que o ADR-0016 rejeitou e o ADR-0023 manteve rejeitado.

## Objetivo de aprendizado

*(campo do `CLAUDE.md` vigente; a emenda proposta o substitui por "Por que
agora")* — relacionamento 1-N no SQLAlchemy 2.0 async com coleção ordenada:
`relationship(order_by=...)`, `selectinload` e por que a coleção não carrega
sozinha no async (o contraste com o lazy loading do EF).

---

## Execução (2026-08-19)

Branch `card-018-turn-com-trechos-de-audio`. Prompt de sessão:
[`docs/prompts/card-018-turn-com-trechos.md`](../prompts/card-018-turn-com-trechos.md).

### O que foi entregue

| Arquivo | O quê |
|---|---|
| `domain/turn.py` | `TurnStage` (enum derivada), `TurnAudioChunk` (`frozen=True`), `Turn.audio_chunks`, `append_audio_chunk`, `stage`, `delivered_partially` |
| `domain/errors.py` | `OutOfOrderAudioChunkError(DomainError)` |
| `adapters/persistence/models.py` | `TurnAudioChunkRow` com PK composta `(turn_id, index)`; relationship com `order_by` + `cascade="all, delete-orphan"` + `lazy="raise_on_sql"` |
| `adapters/persistence/mappers.py` | `chunk_to_row`/`chunk_from_row`, coleção nos 3 sentidos, `_append_new_chunks`, `StaleTurnError` |
| `adapters/persistence/repositories.py` | `selectinload` em `get` **e** `update` |
| `alembic/versions/4600614d460b_*.py` | tabela `turn_audio_chunks`; **`turns` não foi tocada** |
| `tests/domain/test_turn.py` | +16 testes |
| `tests/adapters/test_persistence.py` | +6 testes |

**Decisão fora do card:** `StaleTurnError` em `mappers.py`. Como `apply_turn` só
**acrescenta** trechos, uma entidade defasada não escreveria nada e a divergência
com o banco ficaria invisível. Gatilho para trocar por locking otimista de
verdade: o CARD-009 passar a ter mais de um escritor por turn.

### Critérios de aceite, um a um

**1. Tabela de derivação (4 casos, incluindo trecho-sem-`reply_text`)** ✅

```
tests/domain/test_turn.py::test_etapa_e_transcribing_enquanto_nao_ha_artefato_nenhum
tests/domain/test_turn.py::test_etapa_e_thinking_com_transcricao_e_sem_trecho
tests/domain/test_turn.py::test_etapa_e_speaking_com_trecho_e_reply_text_ainda_nulo
tests/domain/test_turn.py::test_etapa_e_completed_com_o_audio_inteiro
```

O terceiro é o caso que só existe na cascata: afirma `turn.reply_text is None` e
`stage is SPEAKING`. Sob a tabela do ADR-0016 esse teste seria impossível.

**2. `fail()` com 2 trechos preserva os 2 e marca entrega parcial** ✅
`test_falha_nao_apaga_o_que_o_aluno_ja_ouviu` conta (`len(...) == 2`), não
inspeciona status. Repetido do outro lado do mapeamento em
`test_falha_depois_da_entrega_preserva_os_trechos_no_banco`.

**3. Turn `completed` recusa trecho novo** ✅
`test_turn_completo_recusa_trecho_novo` — `InvalidStateTransitionError`
(subclasse de `DomainError`, ADR-0017) com `action="append_audio_chunk"` e
`state="completed"`.

**4. Índice repetido ou furado falha no domínio E no banco** ✅ (dois testes)
- Domínio: `test_indice_repetido_ou_furado_e_recusado` (parametrizado em
  `0, 2, 5, -1`), com `assert len(turn.audio_chunks) == 1` provando que a
  coleção não foi tocada.
- Banco: `test_indice_repetido_e_recusado_pelo_banco` — `INSERT` cru colidindo
  na PK composta levanta `IntegrityError`.

**5. Cobertura de `domain` ≥ 90%** ✅ — ficou em **100%**:

```
$ uv run coverage report --include="*/domain/*,*/application/*" --fail-under=90
src/voicecoach/domain/errors.py                       13      0      0      0   100%
src/voicecoach/domain/turn.py                         99      0     18      0   100%
TOTAL                                                152      0     24      0   100%
```

### Gates (todos verdes, de `backend/`)

```
$ uv run ruff format --check src tests   → 31 files already formatted
$ uv run ruff check src tests            → All checks passed!
$ uv run mypy                            → Success: no issues found in 31 source files
$ uv run lint-imports                    → Contracts: 4 kept, 0 broken.
$ uv run pytest --cov --cov-fail-under=80
  59 passed in 3.86s
  Required test coverage of 80% reached. Total coverage: 91.01%
```

**Prova de que o `lint-imports` morde** (o código novo não o faria morder
sozinho). Injetado em `domain/turn.py`:

```python
from sqlalchemy.orm import relationship
from voicecoach.adapters.persistence.models import TurnAudioChunkRow
```

```
$ uv run lint-imports ; echo "EXIT REAL: $?"
Camadas apontam para dentro (domain não conhece ninguém) BROKEN
domain é puro: sem framework, sem SDK, sem IO BROKEN
application não conhece framework nem SDK de provider BROKEN
Contracts: 1 kept, 3 broken.
EXIT REAL: 1
```

Revertido em seguida; `Contracts: 4 kept, 0 broken`. Nenhuma dependência nova
entrou neste card — `sqlalchemy` e `alembic` já estavam instaladas **e** já
estavam nas listas `forbidden` desde o CARD-005.

### Item de ADR da DoD (critério escrito, LEARNING-0003)

Conferido contra "Quando um ADR é OBRIGATÓRIO" (`docs/adr/README.md`):

- **Critério 6 — contraria uma convenção estabelecida:** ✅ **aplica-se** →
  [**ADR-0028**](../adr/0028-derivacao-da-etapa-do-turn-mora-no-dominio.md).
  O ADR-0016 §4 e a skill mandavam derivar a etapa na borda (`api/schemas`); o
  ADR-0023 reescreveu a tabela e ficou silencioso sobre o **lugar**. A decisão
  (derivar no `domain`) foi levada ao desenvolvedor antes da primeira linha de
  código e escolhida por ele. O §4 do ADR-0016 foi anotado como revogado.
- **Critérios 2 (fronteira) e 5 (difícil de reverter):** aplicam-se ao formato
  persistido, mas **já estão registrados no ADR-0023**, que nomeia a tabela
  `turn_audio_chunks` e cita esses dois critérios no cabeçalho. Este card
  implementa aquele ADR; não gera um segundo registro da mesma decisão.
- **Critérios 1, 3 e 4:** não se aplicam — sem dependência nova, sem custo
  recorrente novo, sem exposição de mídia (é o ADR-0024).

### Regra do explicador — desfecho

Fila de `docs/perguntas-em-aberto.md`: **o arquivo não existia**, logo não havia
pergunta a reapresentar na abertura. Nada a fechar de sessões anteriores.

| # | Pergunta (no ponto da decisão) | Desfecho |
|---|---|---|
| Q1 | Onde mora a derivação de `stage` — `domain` ou borda —, dado que o ADR-0023 reescreveu a tabela e não repetiu o "na borda" do ADR-0016 §4? Perguntada **antes** de escrever `domain/turn.py` | **respondida** — escolheu `domain` (opção A), ciente de que isso obrigava a escrever o ADR-0028 |
| Q2 | *"O que quebra, e com que mensagem, se o `get()` não usar `selectinload`?"* — múltipla escolha, perguntada **antes** de escrever `mappers.py`/`repositories.py` | **respondida, correta**: "(c), com `MissingGreenlet`" |

Q2 foi conferida rodando, com o repositório deliberadamente ainda **sem**
`selectinload`:

```
E  sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called;
   can't call await_only() here. Was IO attempted in an unexpected place?
```

Nenhuma pergunta ficou em aberto; `docs/perguntas-em-aberto.md` segue inexistente.

### Dívidas explícitas

| Dívida | Gatilho / dono |
|---|---|
| A skill `voicecoach-arquitetura` ainda não reflete os **ADRs 0024–0027**. Neste card só foram corrigidas as linhas que **contradiziam** o código (etapa na borda, `speaking` vindo de `reply_text`, referências ao ADR-0016), com as três entradas no log do `REFERENCE.md` | CARD-004 |
| `StaleTurnError` é guarda de defasagem, **não** locking otimista: não há versionamento de linha | CARD-009, se houver mais de um escritor por turn |
| `TurnStage` e `TurnStatus` são duas enums parecidas, com `completed` em ambas — confusão previsível, mitigada só por docstring | registrado como consequência negativa do ADR-0028 |
| A derivação ainda não é consumida por ninguém: `api/schemas` só vai projetar `turn.stage` no CARD-010 | CARD-010 |
| `lazy="raise_on_sql"` no relationship é convenção nova do repositório, adotada com evidência mas sem ADR (escolha local e reversível — não bate nenhum critério da lista) | reavaliar se virar padrão para outros relacionamentos |
