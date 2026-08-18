# CARD-005 — Domínio mínimo e primeiras migrations (Student, Session, Turn)

- **ID:** CARD-005 · **Épico:** Fase 1 — Fatia vertical
- **Plataforma:** backend · **Esforço:** M · **Status:** **concluído**
- **Dependências:** CARD-002, CARD-003

## Contexto

ADR-0004 (Postgres + SQLAlchemy 2.0 async + Alembic). A fatia vertical
precisa de: um Student de desenvolvimento (seed — auth real é Fase 3),
Session e Turn com ciclo de vida de processamento (ADR-0003: estados que não
assumem atomicidade).

## Problema

Nada persiste; o polling do cliente (CARD-010) precisa de um Turn com status
consultável.

## Proposta técnica

- `domain/`: entidades puras `Student`, `Session`, `Turn` (dataclasses) e
  regras de transição como métodos — sem SQLAlchemy aqui.
  **Ajustado na execução:** os estados do Turn passaram a ser
  `queued → processing → completed | failed` **com a etapa derivada dos
  artefatos**, não `pending → processing → …` com a etapa adivinhada
  ([ADR-0016](../adr/0016-ciclo-de-vida-do-turn-estado-grosso-e-etapa-derivada.md));
  entram também `audio_duration` no Turn e o ciclo de vida da `Session`
  (aprovados pelo desenvolvedor na sessão de reconciliação).
- `application/ports/`: `StudentRepository`, `SessionRepository`,
  `TurnRepository` como `Protocol`.
- `adapters/persistence/`: modelos SQLAlchemy (`Mapped`/`mapped_column`),
  mapeamento entidade↔linha, repositórios concretos, `AsyncSession` por
  request via Depends (unit of work explícito).
- Alembic: init async + migration inicial; seed do Student dev via migration
  de dados ou script.
- Testes: domain puro (transições inválidas de estado); adapters contra
  Postgres real (testcontainers ou compose).

## Escopo

- **In:** o acima. **Out:** Correction/UsageEvent (Fase 2, CARD-013/014);
  qualquer endpoint (CARD-010).

## Critérios de aceite

- **Dado** um Turn `completed`, **quando** se tenta `mark_processing()`,
  **então** o domínio rejeita (teste unit).
- **Dado** `alembic upgrade head` num banco vazio, **então** o esquema sobe e
  o Student dev existe.
- **Dado** o repositório concreto, **quando** salva e recarrega um Turn,
  **então** os campos e o estado sobrevivem ao roundtrip (teste de
  integração).

## Riscos

Mapeamento entidade↔modelo é cerimônia que tenta o atalho "usar o modelo
SQLAlchemy como entidade" — proibição da skill (CARD-004); manter o custo
consciente.

## Objetivo de aprendizado

A diferença entre `AsyncSession` do SQLAlchemy e o DbContext: unit of work
explícito (commit é seu), `expire_on_commit`, identidade de objetos na
session — e por que async session + lazy loading não convivem (carregar
relacionamentos vira decisão explícita).

---

## Execução (2026-08-18)

Antes do código, a sessão fez três coisas que o card não previa e que mudaram o
resultado: um **post-mortem** do mecanismo do explicador ([LEARNING-0004]), uma
**reconciliação entre as telas desenhadas e o domínio**
([`docs/reconciliacao-telas-dominio.md`](../reconciliacao-telas-dominio.md)) e
três ADRs. O achado que mais mexeu no card não veio das telas: veio do próprio
backlog — o **CARD-010 já prometia** status por etapa (`transcribing → thinking
→ speaking → completed`) que o modelo proposto aqui não conseguia produzir.

### O que foi entregue

| Camada | Arquivos |
|---|---|
| `domain/` | `errors.py` (ADR-0017), `student.py`, `session.py`, `turn.py` |
| `application/ports/` | `repositories.py` — três `Protocol` |
| `adapters/persistence/` | `models.py`, `mappers.py`, `repositories.py`, `engine.py`, `seed.py` |
| `alembic/` | `env.py` (async, URL fora do `.ini`), migration de esquema, migration de seed |
| `tests/` | `domain/test_turn.py`, `domain/test_session.py`, `adapters/test_persistence.py` |

### ADRs escritos (critério citado — LEARNING-0003)

Conferido contra a lista "Quando um ADR é OBRIGATÓRIO" de `docs/adr/README.md`:

- **[ADR-0016]** — ciclo de vida do Turn. **Critério 2** ("define ou altera uma
  fronteira: *contrato de API, formato de dados persistidos*" — a máquina de
  estados é as duas coisas) e **critério 5** (reverter custa migration +
  backfill + versão de contrato).
- **[ADR-0017]** — invariante violada é exceção; `Result` segue TBD com gatilho.
  **Critério 2** (como o erro cruza a fronteira entre núcleo e borda) e
  **critério 6** (fecha parcialmente um TBD que a skill declarava em aberto).
- **[ADR-0018]** — testcontainers. **Critério 1** (introduz dependência externa).

### Evidência dos critérios de aceite

**1. Turn `completed` recusa `mark_processing()`** — o teste
`test_turn_completo_recusa_voltar_a_processar` cobre exatamente isso (o método
chama-se `start_processing`):

```
uv run pytest tests/domain -q
21 passed
```

**2. `alembic upgrade head` num banco vazio ⇒ esquema sobe e Student dev existe**

```
INFO  [alembic.runtime.migration] Running upgrade  -> 6dcdc3fe7dd3, esquema inicial
INFO  [alembic.runtime.migration] Running upgrade 6dcdc3fe7dd3 -> d790e74af8f6, seed

                  id                  |       display_name
--------------------------------------+--------------------------
 00000000-0000-0000-0000-000000000001 | Aluno de desenvolvimento
(1 row)
```

Verificado também o ciclo `downgrade base` → `upgrade head`, que só passa por
causa de um ajuste à mão na migration: o autogenerate **não** derruba o `TYPE
turn_status`, e sem isso o segundo upgrade falharia com "type already exists".

**3. Roundtrip do Turn preserva campos e estado** — `test_roundtrip_do_turn_…`
contra Postgres real em container, com `expunge_all()` para forçar leitura do
banco em vez do cache de identidade da sessão.

```
uv run pytest tests/adapters -q
10 passed in 10.64s
```

### Quality gates (todos verdes)

```
ruff format --check src tests   31 files already formatted
ruff check src tests            All checks passed!
mypy                            Success: no issues found in 31 source files
lint-imports                    Contracts: 4 kept, 0 broken.
pytest --cov --cov-fail-under=70   35 passed · Total coverage: 89.27%
coverage (domain+application) --fail-under=90   TOTAL 114 stmts, 0 miss → 100%
```

**O segundo anel deixou de ser dormente:** media zero linha até aqui; agora mede
114 statements reais do núcleo, com 100% de cobertura. Dívida do CARD-003
fechada.

### Prova de que o `lint-imports` morde (ADR-0012)

`sqlalchemy` e `alembic` entraram nas listas `forbidden` de `domain` e
`application` **no mesmo commit** que trouxe a dependência. Demonstração com a
lista ainda desatualizada e depois corrigida, sem mudar mais nada:

```
### lista SEM sqlalchemy, com `from sqlalchemy import select` em application/:
Contracts: 4 kept, 0 broken.        ← verde, com a violação dentro

### lista atualizada, mesma violação:
application não conhece framework nem SDK de provider
voicecoach.application is not allowed to import sqlalchemy:
-   voicecoach.application.violacao_demo -> sqlalchemy (l.1)

### revertido:
Contracts: 4 kept, 0 broken.
```

### Regra do explicador — pelo mecanismo novo ([LEARNING-0004])

Duas perguntas, **no ponto da decisão** e não no fim, ambas sobre consequência
observável e conferidas rodando:

1. **Igualdade de `@dataclass`** (antes de declarar as entidades). Desfecho:
   **não respondida** — o desenvolvedor pediu a comparação com C# antes de
   escolher, o que foi feito com o caso executado (`a == b -> False`;
   `{a, b} -> TypeError: unhashable`). **A execução também derrubou as opções
   que o próprio agente ofereceu** — nenhuma previa o `TypeError`. Fica como
   pergunta em aberto reformulável.
2. **Lista `forbidden` desatualizada** (antes de adicionar `sqlalchemy`) — era a
   **Q8**, herdada do CARD-004. Primeira resposta **errada** ("vermelho, porque
   application não pode importar de adapters"); explicada com a execução acima e
   **reformulada**; segunda resposta **correta**. **Q8 fechada.**

Q7 (o que `Protocol` faz que dispensa Moq) continua aberta: este card não
escreveu fake nenhum — os adapters são testados contra Postgres real. Volta no
CARD-006/007, onde o primeiro fake de porta aparece.

### Dívidas explícitas

| Dívida | Gatilho / quem resolve |
|---|---|
| **`alembic/` fica fora do `ruff`/`mypy` dos gates** (que rodam sobre `src` e `tests`). Foi conferido à mão nesta sessão | Ampliar os comandos do ADR-0015 — decisão para o CARD-009, quando houver mais migrations |
| **Cobertura global travada em 70%, real é 89%** — o ADR-0015 manda travar no valor real para que regressão quebre | Subir o limiar em `pre-commit` + CI; proposto, aguardando decisão |
| **Seed de dev numa migration que rodaria em produção** | Fase 3 (auth real), quando existir Student criado por cadastro |
| **`stage` derivado ainda não existe em código** — o ADR-0016 o define, mas ele mora na borda, e endpoint é Out deste card | CARD-010 |
| **`complete()` não é chamado por ninguém ainda** — o pipeline que orquestra as transições | CARD-009 |
| **"Acerto do dia"** (reforço positivo persistido) não tem card | Fase 6, com o resumo pós-sessão completo — registrado na reconciliação |
| **Sem índice composto para "turns do dia por student"** — a query de quota (CARD-015) vai querer um | CARD-015, quando a query existir e o plano for medido |
