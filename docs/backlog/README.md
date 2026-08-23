# Backlog — Tabela Consolidada

Reconstruído em **2026-08-19** em torno do alvo de produto — *o aluno fala, em
~1,8 s o professor começa a responder em áudio, e o aluno paga por isso*.
O diagnóstico card a card, a ordem e as decisões estão em
[`docs/reconstrucao-backlog-2026-08-19.md`](../reconstrucao-backlog-2026-08-19.md).

> **Regra de desempate desta reconstrução:** se algo tiver que ceder para caber,
> cede **escopo** — nunca latência.

| ID | Título | Fase | Plataforma | Esforço | Dependências | Status |
|---|---|---|---|---|---|---|
| [001](CARD-001-monorepo-e-esqueleto-do-backend.md) | Monorepo e esqueleto do backend em camadas | 0 | infra | M | — | **concluído** |
| [002](CARD-002-docker-compose-config-tipada-health.md) | Docker Compose, config tipada e health check | 0 | infra/backend | M | 001 | **concluído** |
| [003](CARD-003-quality-gates-e-ci.md) | Quality gates: ruff, mypy, pytest, pre-commit, CI | 0 | infra | M | 001 | **concluído** |
| [004](CARD-004-skill-de-arquitetura.md) | Skill de arquitetura derivada dos ADRs | 0 | infra | P | 001, 003 | **concluído** |
| [005](CARD-005-dominio-minimo-e-migrations.md) | Domínio mínimo e migrations (Student, Session, Turn) | 1 | backend | M | 002, 003 | **concluído** |
| [018](CARD-018-turn-com-trechos-de-audio-dominio-e-migration.md) | **Turn com trechos de áudio: domínio, invariantes e migration** | 1 | backend | P | 005, ADR-0023 | **concluído** |
| [006](CARD-006-porta-e-adapter-stt-local.md) | **Porta SpeechToText + adapters `mlx-whisper` e `faster-whisper`** | 1 | backend/IA | M | 001, ADR-0027, ADR-0029 | **concluído** |
| [007](CARD-007-porta-e-adapter-teacher-llm.md) | **TeacherLlm em streaming + parse incremental frase a frase** | 1 | backend/IA | **G** | 002, 006, ADR-0022 | **concluído** |
| [008](CARD-008-adapter-tts-local-e-storage.md) | TTS por sentença + MediaStorage por trecho (**Piper venceu**) | 1 | backend/IA | M | 002, 006, 018 | **concluído** |
| [009](CARD-009-fila-arq-e-worker-pipeline.md) | **Worker em cascata, modelos residentes, entrega parcial** | 1 | backend | **G** | 018, 006, 007, 008 | backlog |
| [010](CARD-010-endpoints-de-turn-idempotencia-polling.md) | Endpoints de Turn: upload, idempotência e SSE | 1 | backend | M | 009, ADR-0026 | backlog |
| [011](CARD-011-app-expo-tela-de-conversa-gravacao.md) | App Expo: tela de conversa e gravação | 1 | mobile | M | 001 | backlog |
| [012](CARD-012-upload-polling-playback.md) | **Upload, consumo do stream e playback encadeado** (fecha a fatia) | 1 | mobile | M | 010, 011 | backlog |
| [014](CARD-014-usage-event-custo-real.md) | UsageEvent: custo real por Turn *(antecipado)* | 2 | backend | P | 009 | backlog |
| [015](CARD-015-quotas-e-kill-switch.md) | Quotas + kill switch *(bloqueante comercial)* | 2 | backend | M | 010, 014 | backlog |
| [017](CARD-017-retencao-lifecycle-delete.md) | Retenção de áudio: lifecycle assimétrico e delete por prefixo | 2 | backend/infra | P | 008, 010 | backlog |
| [019](CARD-019-spike-stt-e-tts-no-aparelho.md) | **Spike:** STT e TTS no aparelho (sem compromisso) | 2 | mobile/IA | P | 012 | backlog |
| [013](CARD-013-corrections-persistidas-e-historico.md) | Corrections persistidas + histórico do banco | 3 | backend | M | 009, 010 | backlog |
| [016](CARD-016-ui-de-correcoes-no-app.md) | UI de correções + resumo de sessão no app | 3 | mobile | M | 012, 013 | backlog |
| — | **Contas e auth de verdade** (ADR-0007) | 3 | backend/mobile | — | Fase 2 | a detalhar |
| [020](CARD-020-planos-assinatura-e-entitlements-no-dominio.md) | Planos, assinatura e entitlements no domínio | 4 | backend | M | 015, auth | backlog |
| [021](CARD-021-canal-de-cobranca-e-provedor-de-pagamento.md) | Canal de cobrança e provedor de pagamento | 4 | backend/cliente | G | 020, **ADR pendente** | **bloqueado** |
| [022](CARD-022-webhooks-de-pagamento-e-reconciliacao.md) | Webhooks de pagamento: idempotência e reconciliação | 4 | backend | M | 021 | backlog |
| [023](CARD-023-gate-de-entitlement-no-turn.md) | Gate de entitlement no POST de turn | 4 | backend | P | 015, 020, 022 | backlog |
| — | Eval harness da IA (executa P5) | 5 | IA | — | Fase 3 | a detalhar |
| — | Web companion — e possível canal de receita | 6 | web | — | Fases 4–5 | a detalhar |
| — | Produto pedagógico completo (CEFR, resumo, tradução) | 7 | mobile/IA | — | Fase 5 | a detalhar |

**Caminho crítico até "roda ponta a ponta em ~1,8 s":**
`018 → 006 → 007 → 008 → 009 → 010 → 012` (com `011` em paralelo desde já).

**Caminho crítico até "e cobra":** o acima `→ 014 → 015 → auth → 020 → 021 →
022 → 023`.

**Paralelizáveis:** 011 é independente de todo o backend; 006 e 008 podem correr
juntos depois do 018; 017 pode correr junto de 014/015.
