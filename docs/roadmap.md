# Roadmap de Execução — Voicecoach

- **Data:** 2026-08-17 · **Sessão:** P3 do harness
- **Consome:** `docs/diagnostico-arquitetural.md`, `docs/visao-produto-e-arquitetura-alvo.md`, ADRs 0001–0011
- **Unidade de estimativa:** sessões de trabalho (não dias)

---

## Decisões de sequenciamento (explícitas, como o harness exige)

### 1. WhatsApp: corte limpo imediato

**Decisão: desligado desde já.** "Desligado" = não exposto (sem ngrok) e sem
manutenção; o código permanece congelado no repositório como **referência
executável local** — quando for preciso demonstrar o produto antes de a fatia
vertical existir, roda-se o protótipo na máquina, sob demanda.

*Justificativa:* zero usuários reais a proteger; mantê-lo vivo exigiria
exposição contínua com F1/F2 sem patch (o veredito revisado mandou não
investir nele); e o custo de mantê-lo como "canal legado" seria pago por
ninguém. A restrição de demonstrabilidade contínua é satisfeita pela execução
local sob demanda — não precisa de canal em produção.

### 2. Backend primeiro vs fatia vertical: fatia vertical fina

**Decisão: fatia vertical atravessando backend + app já na Fase 1** — gravar
áudio no aparelho → API → fila → STT local → Claude → TTS local → ouvir a
resposta no aparelho.

*Justificativa:* o próprio harness lista "backend inteiro antes de existir
cliente" como erro comum — backend sem consumidor real erra contrato e UX. A
fatia também ataca cedo os dois maiores desconhecidos do desenvolvedor
(captura de áudio em RN; pipeline async em Python) e ensina mais por sessão.
O preço: a Fase 0 (fundação) precisa vir antes, curta, para a fatia não
nascer sem camadas nem gates.

### 3. Web vs mobile: mobile primeiro, web depois de auth e eval

**Decisão: mobile na Fase 1; web só na Fase 5.**

*Justificativa:* (a) o mobile é o carro-chefe e concentra o maior risco de
aprendizado — ciclo de feedback lento se descoberto tarde; (b) a web
companion consome **dados acumulados** (histórico, correções, progresso) e
**contas** — só existe de verdade depois das Fases 2–3; (c) o eval (Fase 4)
entra antes da web para proteger o núcleo: qualquer mexida em prompt/modelo
durante o desenvolvimento da web já acontece com baseline.

### Loja: não há fase de loja neste roadmap

Decisão da sessão P2 (visão §E, ADR-0010): **build local, custo R$ 0**.
Gatilhos que criariam a fase (e absorveriam o prazo de revisão externo):
querer que terceiros instalem no iPhone ⇒ TestFlight ($99/ano); faixa interna
do Play ⇒ $25. Registrado para não ser "descoberto no fim" — está
deliberadamente fora, não esquecido.

---

## Regras transversais do roadmap

1. **Toda fase termina com o sistema funcional e demonstrável** — a demo de
   cada fase está declarada no critério de saída.
2. **Correção e segurança antes de features** — na prática: quotas + kill
   switch (Fase 2) antes de qualquer conta adicional (Fase 3); nada de beta
   com terceiros antes da Fase 3.
3. **Cards de fases futuras são detalhados no início da própria fase**
   (just-in-time, via `/card`): cards escritos hoje para a Fase 5 estariam
   desatualizados pelos aprendizados das fases 1–4. O backlog completo desta
   sessão cobre as Fases 0–2 (17 cards); as demais têm escopo definido aqui.
4. **Toda troca de prompt/modelo a partir da Fase 4 exige eval verde**
   (ADR-0009/0010).

---

## Fases

### Fase 0 — Fundação e quality gates (4 sessões) · cards 001–004

**Objetivo:** o esqueleto do repositório e os gates que impedem regressão
silenciosa, antes da primeira linha de feature.

- Inclui a execução da sessão **P4 do harness** (gates, hooks, skill de
  arquitetura) como cards 003–004.
- **Critério de saída:** `docker compose up` sobe Postgres/Redis/MinIO;
  `GET /health` responde; CI roda ruff+mypy+pytest e está verde; pre-commit
  ativo; skill de arquitetura derivada dos ADRs existe em `.claude/skills/`.
- **Demo da fase:** pipeline de CI verde + health check; produto demonstrável
  via protótipo congelado (local).
- **Aprendizado:** empacotamento Python moderno (uv, pyproject, src layout),
  a toolchain (ruff/mypy/pytest ≈ analyzers/format/xUnit), pydantic-settings
  (≈ IOptions), estrutura de camadas em Python.

### Fase 1 — Fatia vertical: o primeiro Turn (8 sessões) · cards 005–012

**Objetivo:** falar inglês com o aparelho e ouvir a resposta do professor —
uma conversa real atravessando app, API, fila, STT local, Claude e TTS local.

- Backend: domínio mínimo (Student seed, Session, Turn com estados),
  portas + adapters (faster-whisper, Anthropic, Kokoro, MinIO), fila arq +
  worker, endpoints de turn com Idempotency-Key e polling. Auth ainda é token
  fixo de dev (auth real é Fase 3 — risco aceitável: tudo local, por convite).
- Mobile: app Expo com tela de conversa, gravação com limite de duração,
  upload com retry, polling com backoff, playback.
- **Critério de saída:** no aparelho físico, gravar uma frase em inglês e:
  **ver transcrição + feedback em ≤ ~6s** e **ouvir a resposta em ≤ ~15s**
  (p50 na máquina de dev, com entrega progressiva — texto antes do áudio;
  30s é teto de falha, não meta), com o turn persistido no Postgres; testes
  das camadas domain/application verdes no CI. Medição ponta a ponta
  registrada (CARD-012).
- **Demo da fase:** a conversa no aparelho. A partir daqui o protótipo
  WhatsApp deixa de ser a demo do produto.
- **Aprendizado:** SQLAlchemy 2.0 async + Alembic, `Protocol` como porta,
  arq, FastAPI com DI, multipart/idempotência; expo-audio, permissões,
  FormData e estados async em React Native.

### Fase 2 — Domínio pedagógico + proteção de custo (5 sessões) · cards 013–017

**Objetivo:** transformar resposta em dado pedagógico persistente e fechar a
torneira de custo.

- Corrections tipadas persistidas; histórico do LLM lido do banco;
  UsageEvent com custo real por turn; quotas em minutos/dia + kill switch
  diário/mensal (ADR-0010); URLs assinadas com TTL + retenção/lifecycle +
  delete por prefixo (ADR-0006); correções visíveis no app com resumo de
  sessão.
- **Critério de saída:** correções aparecem estruturadas no app; custo por
  turn/usuário consultável via SQL; estourar a quota bloqueia com erro
  honesto (testado); áudio antigo expira.
- **Demo da fase:** sessão de prática completa com correções no aparelho +
  query de custo.
- **Aprendizado:** relacionamentos e agregações no SQLAlchemy, Redis atômico
  (INCR/TTL), lifecycle S3; renderização de listas/estados no RN.

### Fase 3 — Contas e auth de verdade (4 sessões) · detalhar via /card

**Objetivo:** múltiplos usuários isolados com o fluxo de auth do ADR-0007.

- Registro com código de convite (ADR-0010), argon2id, JWT 15min + refresh
  rotativo com detecção de reuso, expo-secure-store, telas de
  login/registro, isolamento por `student_id` em todas as queries.
- **Critério de saída:** duas contas no mesmo backend sem vazamento de dados
  entre elas (teste de autorização automatizado); token expirado renova
  transparente no app; reuso de refresh revoga a família (testado).
- **Aprendizado:** o ciclo completo de auth de API em Python + secure
  storage e interceptor de refresh no cliente.

### Fase 4 — Eval harness da IA (4 sessões) · executa P5, cards do P5

**Objetivo:** baseline mensurável da qualidade pedagógica antes de qualquer
refinamento de prompt/modelo.

- Sessão P5 do harness roda aqui: dataset versionado, métricas (recall de
  correção, falso positivo, aderência CEFR, formato, latência/custo),
  LLM-as-judge com viés documentado, comando único de regressão vs baseline,
  gate no CI.
- **Critério de saída:** `make eval` (ou equivalente) produz relatório
  comparando prompt/modelo atual vs baseline; CI bloqueia regressão acima do
  limiar; baseline registrado para Haiku (dev) e Sonnet (qualidade).
- **Aprendizado:** engenharia de avaliação de LLM — a peça de portfólio que
  diferencia "app que chama LLM" de produto de IA.

### Fase 5 — Web companion (6 sessões) · detalhar via /card

**Objetivo:** o dashboard que dá sentido aos dados acumulados.

- Vite + React + TS no monorepo; `packages/api-client` com tipos gerados
  (ADR-0008, geração no CI desde a Fase 0); login; histórico de sessões com
  transcrições e correções filtráveis; dashboard de progresso (correções por
  tipo no tempo, CEFR); export/delete de conta (LGPD, visão §E).
- **Critério de saída:** fluxo completo no browser: logar → navegar
  histórico → ver progresso → exportar dados → excluir conta (e o backend
  apaga banco + storage — testado).
- **Aprendizado:** React web real (router, TanStack Query, Recharts), consumo
  de tipos gerados, monorepo pnpm.

### Fase 6 — Produto pedagógico completo no mobile (4 sessões) · detalhar via /card

**Objetivo:** o MVP da visão §A por inteiro.

- Sessões explícitas com resumo pós-sessão; estimativa CEFR como faixa
  (ASSISTANT_MODEL, ADR-0009); tradução on-demand; estados de
  erro/offline/URL expirada polidos.
- **Critério de saída:** o MVP definido na visão §A está integralmente no
  ar; uso próprio regular sem intervenção manual.
- **Aprendizado:** consolidação — a fase onde o app deixa de ser tela de
  teste e vira produto.

### Pós-roadmap (gatilhos, não fases)

| Item | Gatilho (fonte) |
|---|---|
| Revisão espaçada + ErrorPattern | ~50+ Corrections reais (visão §A) |
| Push notifications | revisão espaçada implementada (visão §F) |
| V2 realtime | V1 estável + eval baseline + uso regular (ADR-0003) |
| TestFlight / Play interna | terceiros instalando (visão §E) |
| Beta aberto (e-mail verificado, sem convite) | decisão de abrir (ADR-0010) |

**Total estimado: ~35 sessões** (17 com card escrito; 18 a detalhar
just-in-time nas Fases 3–6).
