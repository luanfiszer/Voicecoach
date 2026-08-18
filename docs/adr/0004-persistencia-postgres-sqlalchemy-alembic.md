# ADR-0004 — Persistência: PostgreSQL + SQLAlchemy 2.0 (async) + Alembic

- **Status:** aceito
- **Data:** 2026-08-17

## Contexto

O diagnóstico (F5) mostrou que todo o estado vive em memória de processo. O
produto exige persistir Student, Session, Turn, Correction, UsageEvent. O
desenvolvedor vem de EF Core + Migrations e quer aprender o par canônico do
ecossistema Python. Infra: Docker Compose local + free tier eventual.

## Decisão

- **PostgreSQL 16** como banco único (relacional; JSONB onde o payload for
  naturalmente documento, ex.: feedback bruto do LLM).
- **SQLAlchemy 2.0 em modo async** com a API declarativa tipada
  (`Mapped[...]`/`mapped_column`) — o par mental de DbContext/DbSet é
  `Session`/repositórios próprios na camada de adapters.
- **Alembic** para migrations versionadas (≈ `dotnet ef migrations`).
- Repositórios definidos como portas (`Protocol`) em `application/`,
  implementados em `adapters/` — domínio não importa SQLAlchemy.

## Alternativas consideradas

### Alternativa A — SQLite (+ SQLAlchemy)
- O que é: banco em arquivo, zero infra.
- Por que foi rejeitada: perde o aprendizado de Postgres (o banco que
  entrevistas e produção usam), concorrência de escrita limitada para
  API + worker simultâneos, e migrar depois custa uma sessão que o Docker
  Compose elimina hoje. Permanece útil como banco de testes rápidos quando
  couber.

### Alternativa B — SQLModel
- O que é: camada do autor do FastAPI unindo pydantic + SQLAlchemy num só
  modelo.
- Por que foi rejeitada: esconde exatamente o que se quer aprender (session,
  unit of work, expiração de objetos, lazy loading) e mistura contrato de API
  com modelo de persistência — acoplamento que a arquitetura em camadas
  proíbe. Modelos pydantic (borda) e modelos SQLAlchemy (adapters) ficam
  separados de propósito.

### Alternativa C — MongoDB
- O que é: documento nativo, sem migrations formais.
- Por que foi rejeitada: os dados são relacionais por natureza (Session 1-N
  Turn 1-N Correction, agregações por tipo de erro para o dashboard);
  relatórios de progresso são queries relacionais. JSONB do Postgres cobre a
  parte documental sem abrir mão de joins.

## Consequências

**Positivas**: aprendizado do par canônico (SQLAlchemy/Alembic ≈ EF
Core/Migrations); queries de dashboard naturais; JSONB dá válvula de escape
documental; async alinhado ao stack.

**Negativas — o preço aceito**: SQLAlchemy 2.0 async tem curva real
(greenlet, sessões por request, expire_on_commit) — é justamente o objetivo
de aprendizado; Postgres no Compose é mais um serviço para orquestrar;
repositórios como portas adicionam uma camada que um CRUD simples não pediria
— paga-se pela testabilidade (fakes em memória) e pelo currículo.

**Equivalente mental .NET:** EF Core + Migrations; a diferença didática
central é que a `AsyncSession` do SQLAlchemy é unit of work explícito — o
commit é seu, não de um SaveChanges implícito em pipeline.
