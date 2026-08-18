# Visão de Produto e Arquitetura Alvo — Voicecoach

- **Data:** 2026-08-17
- **Sessão:** P2 do harness — consome `docs/diagnostico-arquitetural.md` (revisado pelo ADR-0001)
- **Premissas de escopo confirmadas com o desenvolvedor nesta sessão:**
  1. WhatsApp/Twilio descontinuados; núcleo pedagógico preservado (ADR-0001)
  2. Mobile (iOS/Android) é o carro-chefe; web é companion
  3. **Distribuição: build local** (Expo dev build / APK); loja adiada com gatilhos documentados (§E)
  4. **Infra: local + free tiers** (Docker Compose; free tier só quando precisar de demo remota)
  5. **Realtime é ambição real**: V1 turn-based desenhado para o V2 não exigir reescrita (ADR-0003)
- **ADRs gerados nesta sessão:** 0002–0009 (ver `docs/adr/README.md`)

---

## Parte A — Produto

### O que o produto é

**Voicecoach: tutor pessoal de inglês por conversa de áudio, com feedback
estruturado e progresso mensurável.** A diferença para "um bot que responde
áudio": cada conversa produz **dados pedagógicos persistentes** (correções
tipadas, padrões de erro, estimativa de nível) que alimentam a experiência
seguinte. O produto é o ciclo conversa → correção → acúmulo → revisão →
progresso visível, não a resposta isolada.

### Conceitos de domínio (a linguagem ubíqua nasce aqui)

| Conceito | O que é | Observação |
|---|---|---|
| **Student** (conta) | O usuário autenticado, com nível CEFR estimado e quotas | Substitui o número de telefone |
| **Session** | Uma conversa com início e fim explícitos | Não existia no WhatsApp (era thread infinito) — é a unidade de relatório |
| **Turn** | Um ciclo aluno-fala → professor-responde dentro de uma Session | Carrega áudio, transcrição, resposta e custo |
| **Correction** | Correção estruturada de um Turn: `{tipo do erro, trecho original, forma correta, explicação, severidade}` | Deixa de ser texto formatado; vira dado consultável |
| **ErrorPattern** | Agregação de Corrections recorrentes do mesmo tipo/estrutura | Base da revisão espaçada — pós-MVP |
| **CefrAssessment** | Estimativa de nível (A1–C2) com confiança, reavaliada por janela de sessões | Apresentada como faixa ("A2–B1"), nunca como veredito psicométrico |
| **UsageEvent** | Registro de custo real (segundos de STT, tokens, chars de TTS) por Turn | A métrica de custo por usuário nasce no domínio, não no dashboard |

### Crítica à lista proposta

- **Nível CEFR estimado** — entra no MVP na forma barata: estimativa por LLM
  com confiança, recalculada a cada N turns. A versão "reavaliada ao longo do
  tempo com histórico" é evolução natural, não precisa de nada além dos dados
  que já persistimos.
- **Sessões e turnos persistidos** — entra; é a fundação de todo o resto.
- **Correções estruturadas** — entra; é a mudança mais valiosa vinda do
  protótipo (o prompt já pede JSON — falta tipar, persistir e exibir).
- **Erros recorrentes + revisão espaçada** — **corta do MVP.** Exige massa de
  Corrections acumulada para ter o que revisar; construída antes disso é
  feature vazia. Gatilho de entrada: ~50+ Corrections reais de um usuário.
- **Trilha/objetivos de estudo** — **corta.** É a única feature da lista que
  exige curadoria de conteúdo (não emerge da conversa). Gatilho: produto usado
  regularmente e demanda percebida por direção, não só prática livre.
- **Relatório de progresso** — entra em versão mínima (contagens e tendência
  de Corrections por tipo, nível estimado ao longo do tempo). Gráficos ricos
  são a razão de ser da web companion e crescem lá.

### Divisão de responsabilidade entre plataformas

| Capacidade | Mobile | Web | Justificativa |
|---|---|---|---|
| Conversa por áudio (sessão ao vivo) | ✅ único | ❌ | Contexto de uso: praticar fala é ato privado, espontâneo, de fone no ouvido — celular. Áudio no browser fica fora do foco (declarado no escopo) |
| Cadastro, login, gestão de conta | ✅ | ✅ | Conta nasce onde o usuário chega primeiro |
| Resumo pós-sessão (correções do dia) | ✅ | ✅ | No mobile é o fechamento do loop de prática; na web é entrada do histórico |
| Histórico completo navegável (sessões, transcrições, áudios) | resumido | ✅ completo | Ler transcrição e revisar erro é tarefa de tela grande e tempo dedicado |
| Dashboard de progresso (gráficos, tendências, CEFR ao longo do tempo) | mini-resumo | ✅ completo | Gráficos ricos usam o ecossistema web (ver ADR-0002) |
| Export de dados / exclusão de conta (LGPD) | ❌ | ✅ | Operação rara, burocrática — web |
| Push / lembrete de prática | ✅ (pós-MVP) | ❌ | Só faz sentido no device |

Regra aplicada: **nada é replicado por simetria** — cada capacidade mora onde
o contexto de uso manda, e o resumo pós-sessão é a única sobreposição real.

### MVP defensável

O menor conjunto que já é um produto (cada item com o porquê de não ser cortado):

1. **Conta com e-mail verificado + quotas + kill switch de custo** — bloqueante
   herdado do diagnóstico §7.3; sem isso não existe nem beta.
2. **Sessão de conversa turn-based no app**: gravar → enviar → processar
   (STT→LLM→TTS assíncrono) → ouvir resposta + ver correções estruturadas.
   É o núcleo pedagógico portado do protótipo, agora com sessão explícita.
3. **Correções persistidas e tipadas** — sem elas o produto volta a ser
   "bot que responde áudio".
4. **Histórico**: lista de sessões no mobile (resumo) e na web (completo, com
   transcrições e correções filtráveis).
5. **Estimativa CEFR como faixa** + contagem de correções por tipo — o
   progresso mínimo visível que justifica a web companion existir.

**Cortes do MVP** (cada um com gatilho): revisão espaçada e ErrorPattern
(gatilho: massa de correções), trilhas (curadoria), push (gatilho: revisão
espaçada precisa reengajar), realtime (ADR-0003), tradução automática de toda
resposta (on-demand desde o dia 1 — lição do diagnóstico §7.4), gamificação
(streaks etc. — só depois de valor pedagógico comprovado), prática por áudio
na web.

---

## Parte B — Stack de cliente

**Decisão (ADR-0002): Expo/React Native para mobile + web separada
(Vite + React) em monorepo pnpm com pacote compartilhado de tipos e client
de API gerados do OpenAPI.**

Resumo dos trade-offs (análise completa no ADR):

- **react-native-web reprovado para o dashboard**: o ecossistema de gráficos e
  tabelas que faz uma web companion valer a pena (Recharts/visx, tabelas com
  filtro) é web-nativo; em RN-web vira gambiarra de portabilidade. E aprender
  "React web de verdade" é metade do objetivo declarado — RN-web ensinaria um
  dialeto.
- **Nativo (Swift/Kotlin) reprovado**: dobra o currículo sem reuso de React.
  Fica registrado o gatilho técnico real: se o V2 realtime exigir controle de
  áudio abaixo do que módulos nativos do ecossistema Expo/RN oferecem.
- **Flutter reprovado**: Dart; fora do objetivo React por definição.
- **Áudio no Expo**: `expo-audio` cobre gravação (AAC/m4a, suficiente para
  STT) e playback no V1. O V2 realtime exigirá dev build com módulo nativo
  (ex.: WebRTC) — sai do Expo Go, não sai do Expo (ver ADR-0003).
- **Contratos backend→clientes**: FastAPI já publica OpenAPI; geração de tipos
  TypeScript via `openapi-typescript` (tipos puros, zero runtime) no pacote
  `packages/api-client`. Detalhes e alternativas no ADR-0008.

---

## Parte C — Modelo de interação: turn-based vs realtime

**Decisão (ADR-0003): V1 turn-based com costuras pagas conscientemente para o
V2 realtime.**

O essencial (análise completa no ADR):

- **O que muda de V1 para V2 no backend**: transporte (HTTP upload + polling →
  WebSocket/WebRTC bidirecional), STT (batch → incremental), TTS (arquivo →
  stream de chunks), orquestração (job discreto → pipeline contínuo com
  detecção de fim de fala e interrupção).
- **O que sobrevive intacto**: domínio (Session/Turn/Correction), auth,
  persistência, quotas/custo, eval harness, observabilidade — e as **portas**
  de STT/LLM/TTS, se definidas como interface desde o V1.
- **Estimativa de descarte V1→V2: ~15–20%** (endpoints de upload/polling e a
  variante batch dos adapters) — aceitável e consciente.
- **A costura barata que o V1 já paga**: portas de STT/TTS desenhadas para
  ganhar variante streaming por extensão (não por quebra); `Turn` modelado sem
  assumir atomicidade (o V2 introduz turns parciais/interrompidos); transporte
  isolado na borda para ser trocável.
- **A costura que o V1 NÃO paga**: WebSocket no V1 só para "preparar terreno"
  — polling de status resolve o V1 com muito menos superfície; o transporte é
  descartável por desenho.

---

## Parte D — Arquitetura alvo do backend

### Camadas

```
backend/
├── src/voicecoach/
│   ├── domain/          # Entidades, value objects, regras puras.
│   │                    #   PROIBIDO: qualquer import de framework, SDK, IO.
│   ├── application/     # Casos de uso (handlers CQS), portas (Protocols),
│   │                    #   Result. Orquestra domínio + portas.
│   │                    #   PROIBIDO: FastAPI, SQLAlchemy, SDKs de IA.
│   ├── adapters/        # Implementações das portas: repositórios SQLAlchemy,
│   │                    #   STT/LLM/TTS (OpenAI/Anthropic), storage S3,
│   │                    #   fila arq, Redis.
│   ├── api/             # FastAPI: routers, schemas pydantic (contrato),
│   │                    #   auth, exception handlers (Problem Details).
│   └── worker/          # Entrypoint do worker arq (consome a fila).
├── tests/               # Espelha as camadas (ver estratégia abaixo)
└── alembic/             # Migrations
```

Equivalente mental .NET: Domain / Application / Infrastructure / API — com
`worker/` como o host do BackgroundService. O mapa de dependências é o mesmo:
tudo aponta para dentro; `domain` não conhece ninguém.

### Portas (a fronteira que permite trocar provider sem tocar domínio)

Definidas em `application/ports/` como `Protocol` (interface estrutural do
Python — ver diagnóstico §4):

- `SpeechToText` — `transcribe(audio) -> Transcript`; o V2 adiciona
  `stream_transcribe(...)` por extensão
- `TeacherLlm` — `respond(history, student_profile) -> TeacherFeedback`
- `TextToSpeech` — `synthesize(text) -> AudioRef`; V2 adiciona streaming
- `MediaStorage` — `put/get_signed_url(ttl)`
- `TurnQueue` — `enqueue(turn_id)`

Implementações atuais: Whisper, Claude (ADR-0009), OpenAI TTS, MinIO/S3, arq.
Trocar OpenAI por ElevenLabs = novo adapter, zero mudança acima.

### Fluxo de um Turn (V1)

```
app: grava áudio (limita DURAÇÃO na captura — não MB)
  → POST /v1/sessions/{id}/turns  (multipart + Idempotency-Key)
      api: auth → quota check → salva áudio no storage → cria Turn(status=processing)
           → enfileira → 202 {turn_id}
  → worker: STT → LLM (correções estruturadas) → TTS → persiste Turn completo
           + Corrections + UsageEvent(custo real)
  → app: GET /v1/turns/{id}  (polling com backoff)
      → 200 {status, transcript, corrections[], reply_text, reply_audio_url(assinada, TTL)}
```

Idempotency-Key por tentativa de envio resolve o retry de rede móvel
(o renascimento do achado F4 do diagnóstico).

### Persistência (ADR-0004)

Postgres 16 + SQLAlchemy 2.0 (async) + Alembic. Modelo inicial:

`students`, `refresh_tokens`, `sessions`, `turns`, `corrections`,
`usage_events`, `quotas`. (`error_patterns` e `review_items` ficam para o
pós-MVP — o modelo não precisa antecipá-los.)

### Fila e worker (ADR-0005)

**arq** sobre Redis: fila assíncrona nativa, worker como processo separado.
Redis já entra para rate limit/idempotência — a fila não adiciona
infraestrutura nova.

### Cache e rate limit distribuído (por conta, não por telefone)

Redis (`redis-py` async): rate limit por conta **e** por IP (janela deslizante),
chaves de idempotência com TTL, contadores de quota diária, orçamento global
do dia (kill switch).

### Storage de mídia (ADR-0006)

MinIO local (API S3) → qualquer S3-compatível depois. Chaves por usuário
(`{student_id}/{turn_id}/…`), **URLs pré-assinadas com TTL curto** para
download no app, lifecycle de expiração dos áudios (retenção definida na
política de privacidade — §E). Resolve o F6 do diagnóstico por desenho.

### Contrato de API e versionamento (ADR-0008)

REST JSON sob `/v1`, OpenAPI gerado pelo FastAPI como fonte da verdade dos
clientes. **Restrição que o mobile impõe**: usuário com app velho não atualiza
quando queremos ⇒ contrato evolui **apenas aditivamente** (campo novo opcional
sim; remover/renomear/mudar semântica não). Breaking change = `/v2` convivendo
com `/v1` + janela de sunset. Endpoint `GET /v1/meta` informa
`min_supported_app_version` para o app forçar atualização em último caso.

### Autenticação e sessão mobile (ADR-0007)

E-mail + senha com verificação obrigatória (parte da proteção de custo).
Access token JWT curto (~15 min) + refresh token **rotativo** com detecção de
reuso, persistido em `expo-secure-store` (Keychain/Keystore — nunca
AsyncStorage). Sem login social no MVP; gatilho para Sign in with Apple:
publicação na App Store com login social de terceiros (regra da Apple).

### Push notifications

**Pós-MVP** (gatilho: revisão espaçada). Quando entrar: Expo Notifications.
Registrado aqui para não ser esquecido, cortado na Parte F.

### Proteção de custo (bloqueante de lançamento — diagnóstico §7.3)

Defesa em camadas, todas por conta/IP (não mais por telefone):

1. E-mail verificado antes do primeiro Turn
2. Quota diária por conta em **minutos de áudio** (ex.: 10 min/dia), mais
   restritiva para contas com <48h
3. Rate limit por conta e por IP (cadastro e turns)
4. `UsageEvent` por Turn com custo real → métrica de custo por usuário/sessão
5. **Kill switch global**: orçamento diário em Redis; excedido ⇒ `503` com
   Problem Details honesto ("daily budget exhausted")
6. Alertas de gasto nos providers; auto-reload desligado nas contas de API

### Observabilidade

- **Logs**: `structlog` (JSON estruturado; ≈ Serilog)
- **Traces**: OpenTelemetry com auto-instrumentação de FastAPI, httpx e
  SQLAlchemy; exporter OTLP para Jaeger no Docker Compose local. O span do
  worker carrega `turn_id`, `student_id`, e os atributos de custo
- **Métrica de custo por usuário/sessão**: a fonte de verdade é a tabela
  `usage_events` (consultável), espelhada como atributos de span. Dashboard
  dedicado só quando houver tráfego que o justifique (Parte F)

### Estratégia de testes por camada

| Camada | Estratégia | Ferramentas |
|---|---|---|
| domain | Unit puro, sem IO, milissegundos | pytest |
| application | Unit com **fakes em memória** das portas (Protocol dispensa mock framework — um fake é uma classe com os métodos certos) | pytest |
| adapters | Integração contra dependências reais em container (Postgres, Redis, MinIO); HTTP de providers interceptado | pytest + testcontainers, respx |
| api | Testes de rota com `httpx.AsyncClient` contra o app; auth incluída | pytest + httpx |
| contrato | Validação do OpenAPI + geração de tipos no CI acusa breaking change | openapi-typescript no CI |
| IA (qualidade pedagógica) | **Não é teste unitário** — é o eval harness do P5, com dataset e baseline | P5 |

---

## Parte E — Entrega e distribuição

Premissa confirmada nesta sessão: **build local; loja adiada.**

| Tema | Decisão | Gatilho para mudar |
|---|---|---|
| Conta Apple ($99/ano) | **Não pagar agora.** Dev build no próprio iPhone com Apple ID gratuito (re-assinatura a cada 7 dias) ou simulador | Querer que um terceiro instale no iPhone dele sem cabo ⇒ TestFlight |
| Conta Google ($25 única) | Não pagar agora. APK/AAB instalável livremente | Querer faixa interna do Play para testers |
| TestFlight / faixa interna | Adiado | Idem acima; ao ativar, absorver o prazo de revisão no roadmap (P3 marca a fase) |
| Publicação real nas lojas | Fora do horizonte atual | Produto com usuários reais além do autor |
| OTA update (EAS Update) | Sem sentido sem distribuição — adiado | Junto com TestFlight |
| **Política de privacidade / LGPD** | **Não adia.** Processamos voz (dado pessoal) mesmo em beta próprio: definir no MVP a retenção de áudio (TTL no storage, ADR-0006), transcrições, direito de exclusão (delete de conta na web) e o texto da política. Nascer certo é mais barato que retrofit | — |

Custo total de distribuição hoje: **R$ 0.**

---

## Parte F — Anti-overengineering

O que foi tentador incluir e **não** entra, com gatilho objetivo:

| Cortado | Por quê agora não | Gatilho objetivo para entrar |
|---|---|---|
| Kubernetes / microserviços | 1 API + 1 worker + compose resolve; microserviço em portfólio solo é red flag | Nunca neste projeto (não há gatilho realista) |
| RabbitMQ | arq/Redis cobre 1 produtor + 1 consumidor | Múltiplos consumidores heterogêneos ou routing complexo |
| WebSocket no V1 | Polling resolve; WS é superfície extra sem feature que o exija | Primeira feature de push real (V2 realtime ou notificação in-app) |
| Realtime (V2) | ADR-0003 | V1 estável + baseline de eval (P5) + uso próprio regular |
| Login social / Sign in with Apple | E-mail+senha basta; Apple só exige com social na App Store | Publicação na App Store com login de terceiro |
| Push notifications | Nada a notificar no MVP | Revisão espaçada implementada |
| Event sourcing / CQRS completo | CQS leve (handlers) dá o aprendizado sem o custo | Não previsto; auditoria regulatória seria o único motivo |
| Cache de resposta de LLM | Conversas não se repetem | Repetição medida em `usage_events` |
| GraphQL | Dois clientes com necessidades próximas; REST+OpenAPI+tipos gerados resolve | Clientes com necessidades de shape divergentes e crônicas |
| Terraform/IaC | Não há cloud paga | Sair do free tier |
| Prometheus + Grafana | structlog + OTel/Jaeger local cobre; dashboard sem tráfego é enfeite | Tráfego real ou necessidade de demo de SRE |
| i18n do app | Público é brasileiro aprendendo inglês | Usuários não-lusófonos |
| Feature flags service | Env vars + `min_supported_app_version` bastam | Experimentos A/B reais |
| Multi-provider de LLM com fallback automático | Uma porta bem desenhada já permite troca manual | SLA que exija failover (não existe SLA) |

---

*Próximo: P3 consome este documento e o diagnóstico para gerar roadmap e backlog.
As decisões de sequenciamento (corte do WhatsApp, fatia vertical, web vs mobile
primeiro) são tomadas lá.*
