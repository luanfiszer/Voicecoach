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
| [025](CARD-025-varredura-de-turns-travados.md) | Varredura de turns travados (job periódico do arq) | 1 | backend | P | 009 | **concluído** — e achou um segundo buraco: o `arq` não retentava exceção comum, então o turn ficava `processing` para sempre pelo caminho normal de falha (ADR-0052) |
| [010](CARD-010-endpoints-de-turn-idempotencia-polling.md) | **Endpoints de Turn: `/v1`, idempotência, Problem Details e SSE** | 1 | backend | M | 009, ADR-0026 | **concluído** |
| [011](CARD-011-app-expo-tela-de-conversa-gravacao.md) | **App Expo: tela de conversa, gravação e os gates do cliente** | 1 | mobile | M | 001 | **concluído** (pendência: permissão negada permanentemente, em aparelho físico) |
| [012](CARD-012-upload-polling-playback.md) | **Upload, consumo do stream e playback encadeado** (fecha a fatia) | 1 | mobile | M | 010, 011 | **concluído com dívida declarada** — p50 de 2,47 s no Simulador (alvo 2,4 s). O aparelho físico está **bloqueado pelo canal** (ADR-0048: Expo Go da loja no SDK 54), não por trabalho pendente |
| [037](CARD-037-development-build-ios-no-aparelho-fisico.md) | **Dev build iOS no aparelho físico** — o card que o ADR-0048 prometeu e nunca existiu | 1 | mobile/infra | M | 011, 012, ADR-0048 | **rodando no iPhone (2026-09-09)** — dev build instalado e assinado (certificado expira **2026-09-16**), fala humana transcrita corretamente pela primeira vez e áudio tocando no aparelho. ADR-0054. **6 de 7 critérios cumpridos**: `p50` **3037 ms** com fala real (Simulador: 2340 ms; alvo 2400 ms) e gap p50 209 ms. A medição mostrou que **o gargalo é o servidor** — 2,4 s dos 3,0 s são "até o primeiro chunk". Falta só a permissão negada permanentemente |
| [014](CARD-014-usage-event-custo-real.md) | UsageEvent: custo real por Turn *(antecipado)* | 2 | backend | P | 009 | **concluído** — custo medido: US$ 0,002678/turn, ~49% abaixo da estimativa (ADR-0051) |
| [026](CARD-026-resiliencia-na-fronteira-externa.md) | **Resiliência na fronteira externa: timeout, retry, breaker, bulkhead** | 2 | backend | M | 009, 012 | **concluído** — a requisição crua estava no professor, não no S3: o adapter não traduzia erro do SDK e o provedor fora do ar atravessava o caso de uso sem virar `failed` (ADR-0053) |
| [038](CARD-038-tunel-e-codigo-de-convite.md) | **Túnel + `INVITE_CODE`**: o backend sai da LAN, e ganha porteiro antes de sair | 2 | backend/infra | M | 037, ADR-0010 | backlog — escolhido **no lugar de deploy** em 2026-09-09: custo zero, mantém o MLX e a latência medida (o servidor Linux cairia para `faster_whisper`) |
| [039](CARD-039-stt-multilingue-com-idioma-detectado.md) | **O STT ouve qualquer idioma** — modelo multilíngue, idioma detectado, e o `Transcript` para de descartar confiança e segmentos | 2 | backend/IA | M | ADR-0055, ADR-0056 | **concluído (2026-09-13)** — modelos trocados, `stt_language` configurável, `Transcript`/`Segment` na forma do ADR-0056, remedido em `docs/medicao-latencia.md` §13 (+0,18 s de detecção, reproduz o ADR-0055); dívida para o CARD-040: limiar de confiança não pode ser número fixo perto de −1,0 |
| [042](CARD-042-regravar-cala-o-professor.md) | **Regravar cala o professor** — o bug do playback que sobrevive ao `limpar()` | 2 | mobile | P | 037, ADR-0047 | **concluído (2026-09-12)** — `remove()` do `expo-audio` não pausa nada (lido no Swift; no iPhone, 1982–1990 ms sem `pause()` e 1–2 ms com). O link **regravar** também não calava, e era provavelmente o gesto da queixa. [ADR-0061](../adr/0061-o-primeiro-teste-do-cliente-vitest-sobre-logica-extraida.md), [LEARNING-0006](../learnings/0006-remove-nao-e-dispose-e-o-gate-que-faltava-era-o-teste.md), [LEARNING-0007](../learnings/0007-o-relato-dizia-recomecar-e-a-investigacao-mapeou-um-gesto-so.md) |
| [040](CARD-040-nao-entendi-como-desfecho-do-turn.md) | **"Não entendi, pode repetir?"** vira desfecho de turn — e custa zero | 2 | backend/mobile | M | 039, ADR-0057 | backlog — corta antes do professor: turn recusado não gasta LLM nem TTS |
| [041](CARD-041-o-aluno-falou-portugues-o-professor-trata-isso.md) | **O aluno falou português, e o professor trata isso como professor** (cria o bloco de contexto do prompt) | 2 | backend/IA | M | 039, ADR-0059 | backlog — decisão de produto de 2026-09-09: entender e ensinar, não fingir que ouviu inglês |
| [044](CARD-044-a-voz-do-professor-escolhida-por-escuta.md) | **A voz do professor, escolhida por escuta comparada** | 2 | backend/IA | P | ADR-0032 | backlog — **medido**: trocar entre vozes `medium` é de graça; `high` custa **6,5x** (p50 iria a ~3,6 s). Amostras geradas; falta a escuta |
| [043](CARD-043-cancelar-o-turn-no-servidor.md) | **Cancelar o turn no servidor** — o caminho que o V2 vai cobrar caro | 2 | backend/mobile | M | 042, ADR-0058 | backlog — decidido com o número na mesa (US$ 0,0027/turn abandonado): o motivo é o V2, não a economia |
| [045](CARD-045-nivel-declarado-no-onboarding.md) | **O nível declarado pelo aluno entra na conversa** — fecha o buraco visão × backlog | 3 | backend/mobile | M | 041, ADR-0059 | backlog — a visão dizia MVP, o backlog dizia Fase 7, e **não havia card** |
| [046](CARD-046-cefr-assessment-estimado-por-desempenho.md) | **`CefrAssessment`: o nível estimado pelo que o aluno de fato faz** | 3 | backend/IA | **G** | 045, ADR-0049, **ADR pendente** | backlog — **quebrar antes de começar**; o ADR não foi escrito de propósito (sem evidência para decidir janela e algoritmo) |
| [047](CARD-047-mini-teste-inicial-de-nivel.md) | Mini-teste inicial de nível | 7 | mobile/IA | **G** | 045, 046 | **mapeado, sem data prevista** — decisão de 2026-09-09; gatilhos de entrada escritos no card |
| [048](CARD-048-a-voz-da-professora-escolhida-pelo-aluno.md) | **A voz da professora, escolhida pelo aluno** | 7 | backend/mobile | M | 044 | **catalogado, não bloqueia o V1** (decisão de 2026-09-10) — mas o **044 decide o tamanho dele**: `libritts-high` tem **904 vozes num arquivo só**, e aí a feature é um `speaker_id`; voz de falante único a encarece |
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
| [049](CARD-049-cadastro-login-e-o-par-de-tokens.md) | **Cadastro, login e o par de tokens** — a auth que o ADR-0007 desenhou | 3 | backend | M | ADR-0007, **ADR de provedor de e-mail** | backlog — **bloqueante de V1.0 (N3)**. O código de convite do ADR-0010 morre: app público **é** o "beta aberto" do gatilho |
| [050](CARD-050-a-sessao-autenticada-no-cliente.md) | **A sessão autenticada no cliente** — secure storage, refresh e expiração | 3 | mobile | M | 049, ADR-0007 | backlog — **bloqueante de V1.0 (N3)**. O refresh concorrente é o bug que derruba a família de tokens |
| [051](CARD-051-delete-de-conta-dentro-do-app.md) | **Delete de conta dentro do app** | V1 | backend/mobile | M | 049, 050, 017, **ADR novo** | backlog — **bloqueante de V1.0 (N4)**: Guideline 5.1.1(v), reprovação direta. O "não apaga nada" do CARD-032 vale para turn, **não** para conta |
| [052](CARD-052-privacidade-termos-e-rotulos-da-loja.md) | **Política de privacidade, termos e rótulos de privacidade da loja** | V1 | produto/infra | M | 051, 017 | backlog — **bloqueante de V1.0 (N5)**. O risco é invertido: o texto é fácil, o **sistema** é que pode não corresponder |
| [053](CARD-053-conta-apple-build-de-release-e-a-revisao.md) | **Conta Apple, build de release e o caminho até a revisão** | V1 | mobile/infra | M | 051, 052, ADR-0054 | backlog — **bloqueante de V1.0 (N6)**, com prazo que não depende de você. A URL da API fica gravada no build |
| [054](CARD-054-cadastro-aberto-sem-virar-conta-de-custo-aberta.md) | **Cadastro aberto sem virar conta de custo aberta** | V1 | backend | M | 049, 015 | backlog — **bloqueante de V1.0 (N7)**. O kill switch não pode derrubar quem paga, e o `fail-closed` é o oposto do reflexo usual |
| [055](CARD-055-o-backend-sai-do-mac.md) | **O backend sai do Mac** — servidor, domínio, TLS e o primeiro deploy | V1 | infra/backend | M | 024, ADR-0060 | backlog — **bloqueante de V1.0 (N1)** e o de maior incógnita. Achado: **a API não tem `Dockerfile`**, e o compose só tem infra |
| [056](CARD-056-quando-o-servidor-cair.md) | **Quando o servidor cair** — backup, restore testado e log alcançável | V1 | infra | M | 055, ADR-0060 | backlog — **bloqueante de V1.0 (N1)**. O restore **executado** é o único critério que não se cumpre por configuração |
| [057](CARD-057-a-imagem-do-minio-saiu-do-docker-hub.md) | **A imagem do MinIO saiu do Docker Hub** — o CI do backend quebrou e o compose não sobe numa máquina nova | V1 | infra/backend | M | ADR novo (origem da imagem); relac. 055 | backlog — **urgente**: `minio/minio` retorna `denied` desde 2026-09-12 e o job backend falha em **todo** PR (15 `ImageNotFound`). A mesma tag existe em `quay.io`. Inclui o `test_url_assinada_expira` instável, que derrubou o `main` em 10/09 por outra causa |
| [020](CARD-020-planos-assinatura-e-entitlements-no-dominio.md) | Planos, assinatura e entitlements no domínio | 4 | backend | M | 015, auth | backlog |
| [021](CARD-021-canal-de-cobranca-e-provedor-de-pagamento.md) | Canal de cobrança e provedor de pagamento | 4 | backend/cliente | G | 020, **ADR pendente** | **bloqueado — e agora bloqueante da V1.0 (N2)**. A pesquisa virou o primeiro entregável (2026-09-10). **Correção registrada lá:** o IAP **não** é imposto — vender só na web é permitido, o que não se pode é divulgar isso dentro do app |
| [022](CARD-022-webhooks-de-pagamento-e-reconciliacao.md) | Webhooks de pagamento: idempotência e reconciliação | 4 | backend | M | 021 | backlog |
| [023](CARD-023-gate-de-entitlement-no-turn.md) | Gate de entitlement no POST de turn | 4 | backend | P | 015, 020, 022 | backlog |
| — | Eval harness da IA (executa P5) | 5 | IA | — | Fase 3 | a detalhar |
| — | Web companion — e possível canal de receita | 6 | web | — | Fases 4–5 | a detalhar |
| — | Produto pedagógico completo (resumo, revisão espaçada) | 7 | mobile/IA | — | Fase 5 | a detalhar — **o CEFR saiu daqui em 2026-09-09**: virou 045/046/047. A tradução já era o 036 |

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

---

## Corte da V1.0 (2026-09-10)

O backlog foi separado em **impeditivo × não impeditivo** para o lançamento, com
duas premissas confirmadas nesta data: **App Store pública** e **cobrança já na
V1.0**. O documento é
[`docs/corte-v1-o-que-bloqueia-o-lancamento.md`](../corte-v1-o-que-bloqueia-o-lancamento.md).

Resumo do que ele achou: **17 cards existentes são bloqueantes, e sete trabalhos
bloqueantes não têm card nenhum** — deploy do backend (com a queda do `mlx` para
`faster-whisper` fora do Apple Silicon), IAP obrigatório pela Guideline 3.1.1,
auth de verdade, delete de conta (Guideline 5.1.1(v)), política de privacidade e
rótulos, conta Apple e o caminho até a revisão, e proteção de custo no cadastro
aberto.

O alvo **contradiz três decisões aceitas** (ADR-0010, Parte E da visão, e o
CARD-038, que fica substituído pelo card de deploy). Elas precisam de ADR que as
substitua — não de contorno.

---

## A ordem dos cinco pontos da qualidade da conversa (investigação de 2026-09-09)

Origem: [`docs/briefing-qualidade-da-conversa-2026-09-09.md`](../briefing-qualidade-da-conversa-2026-09-09.md),
executado como sessão de investigação em 2026-09-09. **Critério da ordenação:**
custo de implementar × impacto na experiência ÷ risco de latência — com desempate
por *o que estraga a conversa hoje*.

| # | Card | Por que aqui |
|---|---|---|
| 1 | **039** | A causa está medida e a correção principal custa **zero latência**. É o que mais estraga a conversa: o professor respondendo ao que não foi dito. Desbloqueia 040 e 041 |
| 2 | **042** | **Resolve amanhã.** É um bug de cliente, esforço P, e o incômodo é imediato e constante. Só precisa do aparelho |
| 3 | **040** | Fecha a segunda metade do ponto 3 e é a única mudança do lote que **reduz** custo |
| 4 | **041** | Paga a decisão pedagógica do ponto 3 e **constrói o mecanismo** que o 045 reusa |
| 5 | **044** | Esforço P, e a medição já foi feita — falta a escuta, que é decisão do desenvolvedor e não trabalho de engenharia |
| 6 | **043** | Maior que os anteriores e com recuo escrito (ADR-0058, alternativa A). O motivo é o V2, não a economia |
| 7 | **045** | Primeiro card do ponto 5. Depende do mecanismo do 041 |
| 8 | **046** | **G**, e a primeira entrega é um ADR |
| 9 | **047** | Mapeado, sem data |

**Resolve amanhã:** 042 e 039. **É projeto:** 046.

### O que a investigação recomenda NÃO fazer

Aplicando a Parte F da visão ao próprio lote:

- **O ponto 4 (entonação) não vira card.** Os `start`/`end` por segmento entram
  de graça no `Transcript` pelo ADR-0056 e ficam **sem consumidor de propósito**.
  Extrair pitch, energia e taxa de fala (item 1 do briefing) exige biblioteca
  nova, e a pergunta que o próprio briefing levantou continua sem resposta: *o
  que o professor **faria** com isso?* Sem ela, o item vira dado que ninguém usa
  — que é a definição de overengineering neste projeto. **Gatilho de entrada:**
  uma regra pedagógica escrita que use pausa ou ritmo ("você falou muito
  rápido"), e aí o dado já estará lá.
- **Não subir o STT para `medium`.** O ADR-0027 item 7 continua valendo para o
  porte: não há insumo com voz real de aprendiz que o justifique, e ele custa
  latência num orçamento já estourado.
- **Não trocar o motor de TTS.** O ADR-0032 exige as mesmas medições que ele
  fez, e não há evidência nova — a voz não foi sequer comparada ainda (CARD-044).
- **Não fazer barge-in.** É V2 (ADR-0003), e o briefing avisa explicitamente
  para não deixar o CARD-042 virar isso.
- **Não implementar voz por aluno nem sotaque agora** — mas a premissa mudou em
  2026-09-10 e a razão registrada aqui em 2026-09-09 estava **errada**: com um
  modelo multi-falante (`libritts-high`, 904 vozes num arquivo só) a feature
  **não** quebra o modelo residente do ADR-0025 — trocar de voz é um
  `speaker_id: int`. Ela saiu de "não fazer" para **catalogada no CARD-048**,
  fora do V1 por decisão de foco no MVP. O que continua valendo: o **CARD-044
  decide o custo dela**, e sotaque deixa de merecer mecanismo próprio (vira
  outra entrada do catálogo).
