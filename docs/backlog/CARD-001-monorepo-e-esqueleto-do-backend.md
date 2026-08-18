# CARD-001 — Monorepo e esqueleto do backend em camadas

- **ID:** CARD-001 · **Épico:** Fase 0 — Fundação
- **Plataforma:** infra · **Esforço:** M · **Status:** backlog
- **Dependências:** nenhuma

## Contexto

Início da reescrita sobre nova fundação (veredito do diagnóstico). ADR-0002
define monorepo (apps JS + backend Python no mesmo repo); a visão §D define
as camadas.

## Problema

Não existe estrutura: o repositório só tem o protótipo congelado
(`english_teacher_bot/`) e os docs do harness.

## Proposta técnica

- Layout: `backend/` (Python, uv + pyproject, src layout:
  `src/voicecoach/{domain,application,adapters,api,worker}` com `__init__.py`
  e docstring declarando a regra da camada), `apps/mobile`, `apps/web`,
  `packages/api-client` (vazios com README), `pnpm-workspace.yaml`.
- `backend/README.md` com o mapa de dependências entre camadas (tudo aponta
  para dentro) — fonte para a skill de arquitetura (CARD-004).
- uv como gerenciador (lockfile, venv) — equivalente mental: SDK-style
  csproj + NuGet lock.

## Escopo

- **In:** estrutura de pastas, pyproject com deps mínimas (fastapi, pydantic,
  pydantic-settings), workspaces pnpm, READMEs de fronteira.
- **Out:** qualquer endpoint ou lógica (CARD-002+); configuração de CI
  (CARD-003).

## Critérios de aceite

- **Dado** o repo clonado, **quando** `uv sync` roda em `backend/`, **então**
  o ambiente instala e `uv run python -c "import voicecoach"` funciona.
- **Dado** o layout, **quando** se lê o README de qualquer camada, **então**
  a regra de dependência daquela camada está declarada.
- **Dado** a raiz, **quando** `pnpm install` roda, **então** os workspaces
  resolvem sem erro.

## Riscos

Layout de monorepo Python+JS tem armadilhas de tooling (venv vs node_modules
no mesmo repo) — mitigar mantendo cada toolchain no seu diretório.

## Objetivo de aprendizado

Entender o empacotamento Python moderno: por que src layout evita imports
acidentais do diretório de trabalho, o papel do pyproject.toml (≈ csproj) e o
que o uv resolve que pip+venv manuais não resolvem (lockfile determinístico,
≈ NuGet lock + SDK pinning).
