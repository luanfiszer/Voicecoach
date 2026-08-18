# CARD-003 — Quality gates: ruff, mypy estrito, pytest, pre-commit, gitleaks, CI

- **ID:** CARD-003 · **Épico:** Fase 0 — Fundação (executa P4 itens 2–3)
- **Plataforma:** infra · **Esforço:** M · **Status:** backlog
- **Dependências:** CARD-001

## Contexto

O diagnóstico (F12) apontou zero testes e zero gates. O P4 do harness pede
gates automatizados + hooks do Claude Code, para a qualidade não depender de
disciplina. Este card executa essa sessão na prática.

## Problema

Sem gates desde o primeiro card de feature, cada sessão seguinte acumula
dívida invisível — e o Definition of Done do CLAUDE.md fica incobrável.

## Proposta técnica

- **ruff** (lint+format, substitui black/flake8/isort — ≈ dotnet format +
  analyzers) e **mypy --strict** no `backend/` (≈ nullable enable + analyzers
  em warning-as-error).
- **pytest** com layout `tests/{domain,application,adapters,api}` espelhando
  camadas; cobertura mínima nas camadas domain/application (fail under N%).
- **pre-commit**: ruff, mypy, gitleaks (secrets), end-of-file/trailing.
- **GitHub Actions**: job backend (uv sync → ruff → mypy → pytest) + job de
  geração de tipos OpenAPI (placeholder até CARD-010 gerar schema real).
- **Hooks do Claude Code** (P4 item 3): PostToolUse rodando ruff+mypy nos
  arquivos Python editados, para o agente corrigir antes de devolver a tarefa.
- Atualizar Definition of Done no CLAUDE.md: "quality gates passam
  localmente" vira item verificável.

## Escopo

- **In:** tudo acima configurado e rodando verde no repo atual.
- **Out:** skill de arquitetura (CARD-004); gates dos apps JS (entram com os
  apps, Fases 1 e 5).

## Critérios de aceite

- **Dado** um arquivo Python com erro de tipo, **quando** `git commit`,
  **então** o pre-commit bloqueia.
- **Dado** um push, **quando** o CI roda, **então** ruff+mypy+pytest executam
  e o pipeline fica verde no estado atual.
- **Dado** uma edição de arquivo Python pelo agente, **então** o hook roda
  lint/type check e devolve erros na sessão.

## Riscos

mypy strict sobre SQLAlchemy exige plugins/typing cuidadoso — aceitar
overrides pontuais documentados em vez de afrouxar o modo global.

## Objetivo de aprendizado

Mapear a toolchain: por que ruff substituiu três ferramentas (e o que perde),
o que `--strict` do mypy realmente liga, e como pre-commit difere de CI
(gate local vs gate de integração) — o paralelo com analyzers +
warning-as-error + pipeline do mundo .NET.
