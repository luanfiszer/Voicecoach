# CARD-005 — Domínio mínimo e primeiras migrations (Student, Session, Turn)

- **ID:** CARD-005 · **Épico:** Fase 1 — Fatia vertical
- **Plataforma:** backend · **Esforço:** M · **Status:** backlog
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

- `domain/`: entidades puras `Student`, `Session`, `Turn` (dataclasses;
  estados de Turn como Enum: `pending → processing → completed | failed`) e
  regras de transição como métodos — sem SQLAlchemy aqui.
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
