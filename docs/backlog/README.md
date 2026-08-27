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
| [009](CARD-009-fila-arq-e-worker-pipeline.md) | **Worker em cascata, modelos residentes, entrega parcial** | 1 | backend | **G** | 018, 006, 007, 008 | **concluído** |
| [024](CARD-024-dockerfile-do-worker.md) | Dockerfile do worker, com os modelos dentro da imagem | 1 | infra | M | 009 | backlog |
| [025](CARD-025-varredura-de-turns-travados.md) | Varredura de turns travados (job periódico do arq) | 1 | backend | P | 009 | backlog |
| [010](CARD-010-endpoints-de-turn-idempotencia-polling.md) | **Endpoints de Turn: `/v1`, idempotência, Problem Details e SSE** | 1 | backend | M | 009, ADR-0026 | **concluído** |
| [011](CARD-011-app-expo-tela-de-conversa-gravacao.md) | **App Expo: tela de conversa, gravação e os gates do cliente** | 1 | mobile | M | 001 | **concluído** (pendência: permissão negada permanentemente, em aparelho físico) |
| [012](CARD-012-upload-polling-playback.md) | **Upload, consumo do stream e playback encadeado** (fecha a fatia) | 1 | mobile | M | 010, 011 | **concluído com dívida declarada** — p50 de 2,47 s no Simulador (alvo 2,4 s). O aparelho físico está **bloqueado pelo canal** (ADR-0048: Expo Go da loja no SDK 54), não por trabalho pendente |
| [014](CARD-014-usage-event-custo-real.md) | UsageEvent: custo real por Turn *(antecipado)* | 2 | backend | P | 009 | **concluído** — custo medido: US$ 0,002678/turn, ~49% abaixo da estimativa (ADR-0051) |
| [026](CARD-026-resiliencia-na-fronteira-externa.md) | **Resiliência na fronteira externa: timeout, retry, breaker, bulkhead** | 2 | backend | M | 009, 012 | backlog |
| [015](CARD-015-quotas-e-kill-switch.md) | Quotas + kill switch *(bloqueante comercial)* | 2 | backend | M | 010, 014 | backlog |
| [017](CARD-017-retencao-lifecycle-delete.md) | Retenção de áudio: lifecycle assimétrico e delete por prefixo | 2 | backend/infra | P | 008, 010 | backlog |
| [019](CARD-019-spike-stt-e-tts-no-aparelho.md) | **Spike:** STT e TTS no aparelho (sem compromisso) | 2 | mobile/IA | P | 012 | backlog |
| [013](CARD-013-corrections-persistidas-e-historico.md) | **Corrections tipadas persistidas; `feedback` volta na retomada** *(antecipado — rodou antes de 014/015)* | 3 | backend | M | 009, 010 | **concluído** — p50 melhorou para 2,34 s (ADR-0049, ADR-0050) |
| [028](CARD-028-estados-do-turno-redesenhados-contra-a-cascata.md) | **Estados do turno redesenhados contra a cascata** (design × produto) | 2 | mobile/design | P | 012 | backlog |
| [016](CARD-016-ui-de-correcoes-no-app.md) | UI de correções + resumo de sessão no app | 3 | mobile | M | 012, 013 | backlog |
| [027](CARD-027-telas-de-excecao-do-app.md) | **Telas de exceção: offline, quota, pausado, timeout** | 3 | mobile | M | 015, 025, 026 | backlog |
| [029](CARD-029-historico-de-sessoes-no-app.md) | **Histórico de sessões no app** (+ `GET /v1/sessions` e abas) | 3 | backend/mobile | M | 013, 016, 017 | backlog |
| [030](CARD-030-consulta-de-sessoes-listagem-agregada.md) | Backend do histórico: `GET /v1/sessions` agregado + mídia expirada | 3 | backend | M | 013, 017 | backlog |
| [031](CARD-031-ciclo-de-vida-da-sessao-na-borda.md) | Backend do encerrar/offline: `end` na borda + sessão encerrada como `Err` | 3 | backend | M | 010, 013 | backlog |
| [032](CARD-032-descartar-turn-travado.md) | Backend do "Descartar" — **pode morrer no plano**: decidido que não apaga nada | 3 | backend | P | 025 | backlog |
| [033](CARD-033-saldo-de-cota-e-estado-do-servico.md) | Backend do saldo de cota e do serviço pausado (leitura) | 3 | backend | P | 015 | backlog |
| [034](CARD-034-encerramento-automatico-por-inatividade.md) | Encerramento automático da sessão por inatividade (job do arq) | 3 | backend | P | 031, 025 | backlog |
| [035](CARD-035-controles-do-player-sobre-a-fila-de-trechos.md) | Controles do player sobre a fila: `0.75×`, `repetir`, scrub | 3 | mobile | M | 028, 012 | backlog |
| [036](CARD-036-traducao-sob-demanda.md) | Tradução sob demanda: o endpoint do botão `traduzir` | 3 | backend | P | 013, 014, 026 | backlog |
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

**Caminho crítico até "e cobra":** o acima `→ 014 → 026 → 015 → auth → 020 → 021 →
022 → 023`.

**Paralelizáveis:** 011 é independente de todo o backend; 006 e 008 podem correr
juntos depois do 018; 017 pode correr junto de 014/015.

> **Sete decisões de produto foram fechadas em 2026-08-27**, e três delas
> criaram card: o encerramento automático virou o **034**; o scrub (mantido
> junto com `0.75×` e `repetir`) virou o **035**; e o `traduzir`, que o CARD-016
> tratava como condicional, ganhou servidor no **036**. As outras quatro —
> "Descartar" não apaga nada, fala atrasada é recusada, turn em voo conclui
> depois do `end`, e a cota é em minutos com teto duplo — foram registradas nos
> cards que já existiam, e uma delas **encolheu** o 032 a ponto de ele poder
> deixar de existir.

> **Cada tela nova tem o backend dela.** 029 → **030**; 027 (offline) e o
> "Encerrar" do artboard 09 → **031**; 027 (timeout) → **032**; 027 (quota e
> pausado) e o chip de saldo → **033**. Nenhum deles é tela: são regra de
> negócio, contrato e consulta. O **033 depende do 015** decidir a unidade da
> cota — se rodar antes, escolhe por omissão.

> **Os três cards de tela (027, 028, 029) vieram da varredura do design em
> 2026-08-27**, que achou 5 dos 17 artboards sem dono. O 028 abre porque o 016
> renderiza em cima dele; o 027 recolhe as três telas que 012, 015 e a
> reconciliação de 2026-08-18 empurraram para "Out"; o 029 reverte o "Out" do
> 016 sobre histórico — o artboard 10 sempre disse *"consulta rápida; a análise
> completa fica no app web"*, e era o card que estava absoluto demais.

> **026 antes de 015 de propósito:** os dois mexem no mesmo ponto (o POST do
> turn e a saída da cascata), e a ordem importa — cota é proteção *contra o
> cliente*, resiliência é proteção *contra a dependência*. Calibrar limite de
> uso sobre uma fronteira que ainda pode pendurar 60 s é calibrar sobre areia.
