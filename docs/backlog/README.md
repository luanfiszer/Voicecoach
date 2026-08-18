# Backlog — Tabela Consolidada

Gerada na sessão P3 (2026-08-17). Cards das Fases 0–2 escritos; Fases 3–6
são detalhadas **no início da própria fase** via `/card` (regra 3 do
roadmap). Ordem de execução: numérica, respeitando dependências.

| ID | Título | Fase | Plataforma | Esforço | Dependências | Status |
|---|---|---|---|---|---|---|
| [001](CARD-001-monorepo-e-esqueleto-do-backend.md) | Monorepo e esqueleto do backend em camadas | 0 | infra | M | — | **concluído** |
| [002](CARD-002-docker-compose-config-tipada-health.md) | Docker Compose, config tipada e health check | 0 | infra/backend | M | 001 | **concluído** |
| [003](CARD-003-quality-gates-e-ci.md) | Quality gates: ruff, mypy, pytest, pre-commit, CI (P4) | 0 | infra | M | 001 | **concluído** |
| [004](CARD-004-skill-de-arquitetura.md) | Skill de arquitetura derivada dos ADRs (P4) | 0 | infra | P | 001, 003 | **concluído** |
| [005](CARD-005-dominio-minimo-e-migrations.md) | Domínio mínimo e migrations (Student, Session, Turn) | 1 | backend | M | 002, 003 | **concluído** |
| [006](CARD-006-porta-e-adapter-stt-local.md) | Porta SpeechToText + faster-whisper local | 1 | backend/IA | P | 001 | backlog |
| [007](CARD-007-porta-e-adapter-teacher-llm.md) | Porta TeacherLlm + adapter Anthropic estruturado | 1 | backend/IA | M | 002 | backlog |
| [008](CARD-008-adapter-tts-local-e-storage.md) | TTS local (Kokoro) + MediaStorage (MinIO assinado) | 1 | backend/IA | M | 002 | backlog |
| [009](CARD-009-fila-arq-e-worker-pipeline.md) | Fila arq + worker com pipeline do Turn | 1 | backend | M | 005–008 | backlog |
| [010](CARD-010-endpoints-de-turn-idempotencia-polling.md) | Endpoints de Turn: multipart, idempotência, polling | 1 | backend | M | 009 | backlog |
| [011](CARD-011-app-expo-tela-de-conversa-gravacao.md) | App Expo: tela de conversa e gravação | 1 | mobile | M | 001 | backlog |
| [012](CARD-012-upload-polling-playback.md) | Upload com retry, polling, playback (fecha Fase 1) | 1 | mobile | M | 010, 011 | backlog |
| [013](CARD-013-corrections-persistidas-e-historico.md) | Corrections persistidas + histórico do banco | 2 | backend | M | 009, 010 | backlog |
| [014](CARD-014-usage-event-custo-real.md) | UsageEvent: custo real por Turn | 2 | backend | P | 009 | backlog |
| [015](CARD-015-quotas-e-kill-switch.md) | Quotas por conta + kill switch diário/mensal | 2 | backend | M | 010, 014 | backlog |
| [016](CARD-016-ui-de-correcoes-no-app.md) | UI de correções + resumo de sessão no app | 2 | mobile | M | 012, 013 | backlog |
| [017](CARD-017-retencao-lifecycle-delete.md) | Retenção de áudio: lifecycle e delete por prefixo | 2 | backend/infra | P | 008, 010 | backlog |
| — | Fase 3 — Contas e auth (4 sessões) | 3 | backend/mobile | — | Fase 2 | a detalhar |
| — | Fase 4 — Eval harness da IA (4 sessões, executa P5) | 4 | IA | — | Fase 2 | a detalhar |
| — | Fase 5 — Web companion (6 sessões) | 5 | web | — | Fases 3–4 | a detalhar |
| — | Fase 6 — Produto pedagógico completo (4 sessões) | 6 | mobile/IA | — | Fase 4 | a detalhar |

**Caminho crítico:** 001 → 002/003 → 005 → 009 → 010 → 012 (a fatia
vertical). 006/007/008 e 011 são paralelizáveis entre si.
