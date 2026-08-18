# CARD-002 — Docker Compose de dev, configuração tipada e health check

- **ID:** CARD-002 · **Épico:** Fase 0 — Fundação
- **Plataforma:** infra/backend · **Esforço:** M · **Status:** backlog
- **Dependências:** CARD-001

## Contexto

ADR-0004/0005/0006 definem Postgres, Redis e MinIO; ADR-0010 exige tudo
local a custo zero, com Jaeger em profile opcional. O protótipo validava env
vars com `_required()` — o padrão evolui para pydantic-settings (visão §D).

## Problema

Sem infra local reproduzível nem configuração tipada, cada card seguinte
começaria improvisando ambiente.

## Proposta técnica

- `docker-compose.yml`: postgres:16, redis:7, minio (+ console), jaeger sob
  `--profile observability`. Volumes nomeados, healthchecks de container.
- `Settings(BaseSettings)` em `voicecoach.config`: DATABASE_URL, REDIS_URL,
  S3_*, ANTHROPIC_API_KEY, TEACHER_MODEL/ASSISTANT_MODEL (defaults do
  ADR-0009/0010), quotas e budgets (ADR-0010). Falha no boot se faltar
  obrigatória (preserva o fail-fast do protótipo).
- App FastAPI mínimo em `api/` com `GET /health` (liveness) e
  `GET /health/ready` (checa Postgres/Redis/MinIO).
- `.env.example` completo.

## Escopo

- **In:** compose, settings tipadas, health endpoints, primeiro teste de API
  (health) com httpx.
- **Out:** modelos de banco e migrations (CARD-005); CI (CARD-003).

## Critérios de aceite

- **Dado** `docker compose up -d`, **quando** a API sobe, **então**
  `/health/ready` retorna 200 com o status das 3 dependências.
- **Dado** um `.env` sem `ANTHROPIC_API_KEY`, **quando** a API tenta subir,
  **então** falha no boot com mensagem nomeando a variável.
- **Dado** `docker compose --profile observability up`, **então** o Jaeger UI
  responde localmente.

## Riscos

Portas ocupadas na máquina; versões de imagem — fixar tags.

## Objetivo de aprendizado

pydantic-settings como `IOptions<T>` + validação de boot: onde a tipagem
acontece (import time vs runtime), como defaults/env/arquivo se compõem, e o
idioma `model_config`/`SettingsConfigDict` que não tem paralelo direto em C#.
