# Diagnóstico Arquitetural — English Teacher Bot

- **Data:** 2026-08-17
- **Escopo:** todo o código em `english_teacher_bot/` (6 módulos, ~470 linhas)
- **Método:** leitura integral do código, sem execução; preços de API da tabela oficial Anthropic (cache 2026-06) e preços públicos OpenAI/Twilio
- **Sessão:** P1 do harness — nenhuma linha de código foi alterada
- **Revisão 2026-08-17 (P1.5, ADR-0001):** o WhatsApp/Twilio será descontinuado
  em favor de app mobile próprio + web companion. Achados atrelados ao canal
  estão marcados como **OBSOLETO PELO ADR-0001** — nada foi deletado; a análise
  de migração está na seção final "Revisão pós-mudança de escopo", e o Veredito
  (§6) foi reescrito para o novo destino.

---

## 1. Mapa do sistema atual

### Fluxo real de uma requisição (áudio)

```
Twilio POST /webhook (form-encoded)
  └─ main.py:40  form parse
  └─ main.py:50  limits.check()           — allowlist + rate limit + cota diária (memória)
  └─ main.py:60  await _handle_message()  — TUDO INLINE, dentro do request
       └─ audio.py:25  download_twilio_media()   httpx SÍNCRONO, timeout 30s     ~0.3–1s
       └─ audio.py:49  transcribe()              OpenAI Whisper SÍNCRONO         ~2–6s
       └─ teacher.py:80 get_feedback()           Anthropic SÍNCRONO              ~3–8s
       └─ main.py:132  whatsapp.send_text()      Twilio REST SÍNCRONO            ~0.3–0.8s
       └─ audio.py:63  synthesize()              OpenAI TTS SÍNCRONO             ~1–3s
       └─ main.py:139  whatsapp.send_audio()     Twilio REST SÍNCRONO            ~0.3–0.8s
  └─ main.py:69  return "" (200)
```

**Latência estimada do fluxo completo (áudio de ~1 min):**

| Percentil | Estimativa | Consequência |
|---|---|---|
| p50 | ~8–12s | OK por pouco |
| p95 | ~15–25s | **Estoura o timeout de 15s do Twilio** → Twilio marca falha e **reenvia o webhook** |

> **[Nota da revisão ADR-0001]** O timeout do Twilio e seus retries somem com o
> canal, mas o problema de latência **não**: num app mobile o usuário fica
> olhando a tela — 8–25s de espera sem feedback incremental é orçamento de UX
> estourado do mesmo jeito. Muda o juiz (usuário em vez do Twilio), não a falha.

Duas agravantes estruturais:

1. **Todas as chamadas externas são síncronas dentro de um handler `async`** — elas bloqueiam o event loop do Uvicorn. Enquanto uma mensagem é processada, **nenhuma outra requisição é atendida** (nem o health check `/`). A concorrência efetiva do serviço é 1.
2. Não há idempotência (ver 3.c), então o retry do Twilio reprocessa a mensagem inteira: **paga-se duas vezes** e o usuário recebe respostas duplicadas.

### Custo por interação de áudio (~1 min de fala, histórico cheio)

| Etapa | Cálculo | Custo (US$) |
|---|---|---|
| Whisper STT | $0.006/min × 1 min | 0.006 |
| Claude Sonnet (input) | ~2.000 tokens (system ~600 + histórico ~1.300) × $3/MTok | 0.006 |
| Claude Sonnet (output) | ~400 tokens de JSON × $15/MTok | 0.006 |
| OpenAI TTS (`tts-1`) | ~350 chars × $15/M chars | 0.005 |
| Twilio WhatsApp | 2 mensagens outbound (~$0.005 cada + taxas Meta) | ~0.010–0.015 |
| **Total por mensagem** | | **~US$ 0.033–0.038** |

**O número que importa:** com a cota diária de 100 msgs (`config.py:47`), **um único usuário no limite custa ~US$ 3,50/dia ≈ US$ 105/mês**. O `translation_pt` é gerado em **toda** resposta (teacher.py:38) mas só é usado se o usuário pedir `traduzir` — ou seja, ~30–40% dos tokens de output são pagos e descartados na maioria das interações.

---

## 2. Inventário de falhas

Ordenadas por severidade. Formato: severidade · tipo · evidência · cenário de quebra · custo de adiar.

### F1 — Webhook aceita requisições de qualquer origem (sem validação de assinatura)
> **OBSOLETO PELO ADR-0001** — o webhook público morre com o canal; no destino a
> borda é uma API autenticada. Risco residual apenas enquanto o protótipo estiver
> exposto via ngrok — mitigação: não expor, em vez de corrigir.
- **Severidade:** crítica · **Tipo:** segurança + custo
- **Evidência:** `main.py:30-45` — nenhuma verificação de `X-Twilio-Signature`
- **Cenário de quebra:** qualquer pessoa que descubra a URL (ngrok URLs vazam em logs, histórico de browser, scanners) faz `POST /webhook` com `From` e `MediaUrl0` arbitrários. Cada POST custa ~$0.03 e o atacante controla o volume. Um loop de 10 req/s drena o crédito das três contas em horas. O rate limit não protege: o atacante varia o `From` livremente.
- **Custo de adiar:** prejuízo financeiro direto e aberto enquanto o ngrok estiver de pé. Corrigir custa ~20 linhas (o SDK Twilio tem `RequestValidator`).

### F2 — SSRF com vazamento de credenciais Twilio
> **OBSOLETO PELO ADR-0001** — no destino não existe `MediaUrl` vindo de fora: o
> áudio chega por upload autenticado do próprio cliente. Mesmo risco residual do
> F1 enquanto o protótipo rodar exposto. A lição geral (nunca anexar credenciais
> a URLs controladas por terceiros) permanece válida para qualquer adapter futuro.
- **Severidade:** crítica · **Tipo:** segurança
- **Evidência:** `audio.py:31-34` — `client.get(media_url, auth=(SID, AUTH_TOKEN))` com `media_url` vindo **do form da requisição** (`main.py:44`), sem validar o host
- **Cenário de quebra:** combinado com F1, o atacante envia `MediaUrl0=https://atacante.com/x`. O servidor faz GET nessa URL **enviando Account SID + Auth Token em Basic Auth**. Com o token, o atacante controla a conta Twilio inteira: envia mensagens, lê logs, gasta crédito, sequestra o número.
- **Custo de adiar:** é o pior vetor do sistema — comprometimento total da conta Twilio, não só custo. A correção é validar que o host da URL é `api.twilio.com` antes de anexar auth.

### F3 — Chamadas síncronas bloqueiam o event loop
- **Severidade:** crítica · **Tipo:** escalabilidade
- **Evidência:** `audio.py:33` (`httpx.Client` síncrono), `audio.py:53`/`68` (`OpenAI` síncrono), `teacher.py:87` (`Anthropic` síncrono), `whatsapp.py:16`/`25` (Twilio síncrono) — todos chamados dentro de `async def _handle_message` (`main.py:72`)
- **Cenário de quebra:** dois usuários mandam áudio com 5s de diferença. O segundo espera o pipeline inteiro do primeiro (~10–20s) antes de sequer começar. Com 5 usuários simultâneos, o último espera ~1 min e o Twilio já estourou timeout e reenviou tudo — tempestade de retries sobre um servidor que atende 1 requisição por vez.
- **Custo de adiar:** é a falha que transforma "2 usuários" em incidente. Qualquer plano de produto esbarra nela primeiro.

### F4 — Sem idempotência por MessageSid
> **OBSOLETO PELO ADR-0001 (como formulado)** — MessageSid e retry de webhook
> morrem com o Twilio. O **conceito** renasce mais forte no destino: upload de
> áudio de rede móvel exige retry no cliente, logo idempotency key por tentativa
> de envio no backend. O achado vira requisito da nova API, não patch do protótipo.
- **Severidade:** alta · **Tipo:** correção + custo
- **Evidência:** `main.py:40-45` — `MessageSid` nunca é lido do form
- **Cenário de quebra:** p95 > 15s (seção 1) → Twilio reenvia → o mesmo áudio é baixado, transcrito, respondido e sintetizado de novo. Usuário recebe card e áudio duplicados; o histórico ganha turnos duplicados (corrompendo o contexto pedagógico); paga-se 2× por mensagem. Retries em cascata sob carga (F3) multiplicam isso.
- **Custo de adiar:** cresce junto com o tráfego; barato de corrigir agora (um set de SIDs processados), caro de diagnosticar depois ("por que o bot responde duas vezes às vezes?").

### F5 — Todo o estado é em memória de processo
- **Severidade:** alta · **Tipo:** escalabilidade + correção
- **Evidência:** `teacher.py:51-52` (`_history`, `_last_reply`), `limits.py:11-12` (`_minute_window`, `_daily_count`)
- **Cenário de quebra:** (a) restart/deploy → histórico de conversa e **cotas diárias zeram** — usuário que gastou 100 msgs ganha mais 100; (b) `uvicorn --workers 2` → cada worker tem seus próprios dicts: cota efetiva dobra, e o histórico do usuário se fragmenta entre workers (a conversa "esquece" turnos aleatoriamente, dependendo de qual worker atende); (c) os dicts nunca sofrem eviction de usuários antigos — vazamento de memória lento.
- **Custo de adiar:** bloqueia horizontalização e qualquer persistência de produto (sessões, progresso). É a razão de ser do banco na arquitetura alvo.

### F6 — MP3s de resposta públicos, sem expiração e sem limpeza
- **Severidade:** alta · **Tipo:** segurança/privacidade + operação
- **Evidência:** `main.py:22` (`StaticFiles` em `/audio`, sem auth), `audio.py:63-74` (`out_*.mp3` criado e **nunca removido** — só os de entrada são limpos, `main.py:118-119`)
- **Cenário de quebra:** cada resposta do professor (que cita e corrige a fala do aluno — conteúdo pessoal) fica em URL pública para sempre. O UUID dificulta adivinhação, mas as URLs transitam pelo Twilio, aparecem em logs e nunca expiram. Além disso o disco cresce sem limite: ~100 KB/resposta × 100 msgs/dia ≈ 10 MB/dia até encher o volume.
- **Custo de adiar:** privacidade (dados de voz de usuário retidos indefinidamente sem controle) + incidente operacional garantido em meses. A arquitetura alvo pede storage com URL assinada e TTL.

### F7 — Histórico é mutado antes da chamada ao Claude ter sucesso
- **Severidade:** média · **Tipo:** correção
- **Evidência:** `teacher.py:83` — `history.append({"role": "user", ...})` **antes** de `messages.create` (`teacher.py:87`); nenhum rollback no caminho de exceção
- **Cenário de quebra:** Anthropic retorna 429/500 → exceção propaga → o turno do usuário fica órfão no histórico. Na próxima mensagem, o histórico tem dois turnos `user` consecutivos e um contexto que o professor "nunca respondeu" — estado conversacional corrompido silenciosamente. Duas mensagens simultâneas do mesmo usuário também intercalam appends (sem lock).
- **Custo de adiar:** bugs pedagógicos sutis, difíceis de reproduzir. É o argumento concreto para um domínio com invariantes em vez de dicts (3.j).

### F8 — Sem timeout/retry/circuit breaker próprios nas chamadas de IA
- **Severidade:** média · **Tipo:** correção + escalabilidade
- **Evidência:** `teacher.py:87`, `audio.py:53`/`68` — nenhum `timeout=`/`max_retries=` explícito; dependência dos defaults dos SDKs (timeout de ~10 min, 2 retries)
- **Cenário de quebra:** OpenAI degrada e responde em 90s. Com F3, o event loop fica bloqueado 90s; Twilio já reenviou o webhook 2× (F4); o usuário recebeu 3 respostas atrasadas em rajada. O default de 10 min dos SDKs é inaceitável num fluxo cujo orçamento total é 15s.
- **Custo de adiar:** cada incidente de provider vira incidente do bot, amplificado.

### F9 — Falha de JSON do Claude manda texto arbitrário para o TTS
- **Severidade:** média · **Tipo:** correção + custo
- **Evidência:** `teacher.py:97-106` — no `JSONDecodeError`, o texto bruto inteiro vira `spoken_reply` e segue para `audio.synthesize` (`main.py:135-139`)
- **Cenário de quebra:** Claude responde JSON malformado longo (ou prosa) → o bot paga TTS sobre o texto inteiro (TTS cobra por caractere) e o usuário recebe um áudio estranho, possivelmente lendo JSON em voz alta. O fallback também zera `translation_pt` sem sinalizar nada.
- **Custo de adiar:** baixo em dinheiro, alto em qualidade percebida. A solução real é structured output/validação de schema (pydantic) — nativo no ecossistema já instalado.

### F10 — Parsing frágil do form e resposta 500 involuntária
- **Severidade:** baixa · **Tipo:** correção
- **Evidência:** `main.py:43` — `int(form.get("NumMedia") or 0)` levanta `ValueError` se o campo vier malformado; exceção **antes** do try de `_handle_message` → 500 → retry do Twilio (com F4, reprocessamento)
- **Cenário de quebra:** payload fora do padrão (ou forjado, via F1) derruba o handler antes de qualquer proteção.
- **Custo de adiar:** baixo; some de graça quando o contrato do webhook virar modelo pydantic.

### F11 — Cota diária é consumida por mensagens que não custam nada
> **OBSOLETO PELO ADR-0001 (mecanismo)** — comandos por texto mágico ("reset",
> "traduzir") e cota por número de telefone morrem com o canal. A lição
> (contagem de cota ≠ decisão de negócio; cobrar cota só do que custa dinheiro)
> entra no desenho das quotas por conta — que, sem a allowlist, viram bloqueantes
> de lançamento (ver Revisão pós-mudança de escopo).
- **Severidade:** baixa · **Tipo:** correção
- **Evidência:** `limits.py:38` — `check()` incrementa a cota antes de saber o tipo da mensagem; `main.py:50` roda antes da classificação
- **Cenário de quebra:** usuário manda 5 textos "oi" e gasta 5% da cota diária de áudio sem custar um centavo de IA. Inverso do objetivo do limite (proteger custo).
- **Custo de adiar:** baixo; é sintoma de `check()` misturar decisão de negócio com contagem.

### F12 — Nenhum teste, nenhum gate
- **Severidade:** alta (transversal) · **Tipo:** testabilidade/manutenibilidade
- **Evidência:** ausência de `tests/` no repositório; funções acopladas diretamente a clientes globais de SDK (`teacher.py:50`, `audio.py:16`, `whatsapp.py:11`) tornam teste unitário impossível sem monkeypatch
- **Cenário de quebra:** qualquer refatoração (que é o plano inteiro) é feita às cegas. A lógica mais valiosa e testável — formatação de cards, trim de histórico, extração de JSON, limites — não tem uma asserção sequer.
- **Custo de adiar:** cresce a cada sessão; é pré-requisito do roadmap, não um item dele.

---

## 3. Checklist de verificação obrigatória

| # | Hipótese | Veredito | Evidência |
|---|---|---|---|
| a | STT+LLM+TTS síncronos dentro do request? | **CONFIRMADO** — e pior: chamadas síncronas em handler async bloqueiam o event loop (F3). Timeout do Twilio: 15s. p95 estimado do fluxo: 15–25s → retries. *(Revisão ADR-0001: a referência ao Twilio é obsoleta; a latência continua inaceitável para usuário de app olhando a tela)* | `main.py:60`, `audio.py:33,53,68`, `teacher.py:87` |
| b | `X-Twilio-Signature` validada? *(OBSOLETO PELO ADR-0001 — webhook morre com o canal)* | **REFUTADO — não é validada.** Vetor: POST direto com `From`/`MediaUrl0` forjados. Prejuízo: ~$0.03 por request forjada, volume ilimitado (F1) + vazamento do Auth Token via SSRF (F2) | `main.py:30-45`, `audio.py:31-34` |
| c | Idempotência por MessageSid? *(OBSOLETO PELO ADR-0001 — o conceito renasce como idempotency key de upload)* | **REFUTADO — não existe.** Retry do Twilio ⇒ reprocessamento completo: custo 2×, respostas duplicadas, histórico corrompido (F4) | `main.py:40-45` |
| d | Estado sobrevive a restart? Diverge com 2+ workers? | **CONFIRMADO o problema** — nada sobrevive a restart; com N workers há N cotas e N históricos independentes (F5) | `teacher.py:51-52`, `limits.py:11-12` |
| e | MP3 públicos sem auth nem expiração? | **CONFIRMADO** — `StaticFiles` sem auth, URLs eternas com conteúdo derivado da fala do usuário (F6) | `main.py:22`, `audio.py:77-78` |
| f | Limpeza de `temp_audio/`? | **PARCIAL** — inputs são removidos (`main.py:118-119`); **outputs nunca** (F6). ~10 MB/dia no teto da cota; disco enche em meses, não em dias |
| g | Timeout/retry/circuit breaker em OpenAI/Anthropic/Twilio? | **REFUTADO** — só o download Twilio tem timeout explícito (30s, `audio.py:33`). IA usa defaults do SDK (~10 min timeout, 2 retries). Circuit breaker: inexistente (F8) |
| h | OpenAI 429/500 no meio do fluxo → feedback ao usuário? | **PARCIAL** — catch-all em `main.py:61-66` envia "something went wrong". Mas o histórico já foi mutado (F7) e falha parcial (card enviado, TTS falhou) deixa o usuário com resposta pela metade, sem compensação |
| i | Prompt versionado? Como detectar regressão pedagógica? | **REFUTADO** — `SYSTEM_PROMPT` é string em `teacher.py:26-48`; sem versionamento próprio, sem eval, sem baseline. Mudança de prompt hoje é chute (P5 do harness ataca isso) |
| j | Modelo de domínio ou funções sobre dicts? | **CONFIRMADO: só dicts.** O feedback transita como `dict` com `.get(..., "")` defensivo espalhado (`teacher.py:109-121,140-167`, `main.py:125-139`). Nenhum pydantic model, apesar do pydantic já ser dependência transitiva do FastAPI |
| k | Modelo Claude fixado em versão desatualizada? | **CONFIRMADO** — `claude-sonnet-4-20250514` (maio/2025, ~15 meses atrás; `config.py:28`). Gerações atuais: Sonnet 4.6 e Sonnet 5 ($3/$15, Sonnet 5 com preço intro $2/$10 até 2026-08-31) e **Haiku 4.5 ($1/$5)** — candidato natural para tarefas auxiliares. SDK `anthropic==0.34.0` também está ~2 anos defasado. Merece ADR próprio (arquitetura de custo) |

---

## 4. Tradução .NET → Python

| Conceito (.NET) | Equivalente Python recomendado | Por que este e não a alternativa |
|---|---|---|
| DI container (`Microsoft.Extensions.DependencyInjection`) | **FastAPI `Depends`** (nativo) | Resolve por assinatura de função, com escopo por request e override em teste — cobre 95% dos casos. `dependency-injector` (container explícito, mais parecido com .NET) só compensa quando há grafo de dependências fora do ciclo HTTP (workers); reavaliar quando o worker existir |
| ORM + Migrations (EF Core) | **SQLAlchemy 2.0 + Alembic** | Padrão de indústria, async nativo, e o par exato DbContext↔Session / Migrations↔Alembic. `SQLModel` (do autor do FastAPI) é açúcar sobre SQLAlchemy — esconde o que você quer aprender. Django ORM acopla ao framework errado |
| Result Pattern (FluentResults/OneOf) | **Result próprio com `dataclasses` + `typing.Union`**; avaliar `returns` depois | Não há padrão dominante — Python idiomático usa exceções. Um Result caseiro de ~30 linhas ensina generics/`Union`/pattern matching do Python; a lib `returns` (estilo funcional, Maybe/IO) é pesada demais como ponto de partida |
| CQS / handlers (MediatR) | **Dispatcher próprio** (protocolo `Handler` + registro via DI) | Não existe MediatR canônico em Python; os clones (`mediatr-py`) são pequenos e pouco mantidos. Escrever o dispatcher (~50 linhas) ensina `Protocol` (a interface estrutural do Python) e generics — ADR quando chegar lá |
| Validação de contrato (DataAnnotations/FluentValidation) | **pydantic v2** | Já é dependência do FastAPI; valida na borda, gera OpenAPI de graça, e os modelos são o DTO tipado. Equivalente mental: `record` + FluentValidation + ModelBinding num pacote só |
| Mensageria/fila (RabbitMQ + MassTransit) | **arq** (fila sobre Redis, async) para o worker do webhook; RabbitMQ + `aio-pika` se/quando precisar de roteamento real | O problema imediato (tirar o pipeline do request) precisa de fila simples + Redis, que já entra para rate limit. Celery é o "Hangfire+MassTransit" onipresente, mas config pesada e async de segunda classe. ADR obrigatório nesta escolha |
| Cache distribuído (StackExchange.Redis / IDistributedCache) | **redis-py** (async) | Cliente oficial, async nativo. Serve rate limit distribuído (F5), idempotência (F4) e cache |
| Background worker (BackgroundService/Hangfire) | **worker `arq`** (processo separado consumindo a fila) | Mesma decisão da mensageria; um processo `arq` é o `BackgroundService` consumindo fila |
| Testes (xUnit) | **pytest** (+ `pytest-asyncio`) | Padrão absoluto. Fixtures ≈ `IClassFixture`/construtor, `parametrize` ≈ `[Theory]/[InlineData]`, com menos cerimônia |
| Mocks (Moq / WireMock) | **`unittest.mock` (stdlib) + `respx`** para HTTP | `mock`/`monkeypatch` cobrem o papel do Moq (duck typing dispensa interface para mockar — ver nota abaixo); `respx` intercepta `httpx` como WireMock intercepta HttpClient |
| Observabilidade (OTel .NET + Serilog) | **opentelemetry-python + structlog** | OTel é a mesma spec, mesmos exporters. `structlog` ≈ Serilog (log estruturado, processors ≈ enrichers) |
| Health check (`AspNetCore.HealthChecks`) | Endpoint FastAPI próprio (`/health/live`, `/health/ready`) | Não há pacote dominante; o padrão é escrever as rotas — trivial e mais transparente |
| ProblemDetails (RFC 7807 nativo) | **Exception handlers do FastAPI** devolvendo o shape RFC 7807 | As libs (`fastapi-problem`) são pequenas e instáveis; handler próprio de ~30 linhas ensina o mecanismo de middleware/exception handling do framework |
| Configuração tipada (`IOptions<T>`) | **pydantic-settings** (`BaseSettings`) | Substitui o `config.py` atual: classe tipada, validação no boot, `.env` nativo — `IOptions` + DataAnnotations em um |
| Lint/format/análise (dotnet format + analyzers) | **ruff** (lint+format) + **mypy** modo estrito | Detalhado em P4; ruff substituiu black+flake8+isort com uma ferramenta só |

> **Idioma sem paralelo em C# que aparece acima — `Protocol`:** interface **estrutural**: uma classe a satisfaz por ter os métodos com as assinaturas certas, sem declarar `implements`. É o duck typing com verificação estática (mypy). É por isso que mockar em Python não exige extrair interface: qualquer objeto com o método certo serve.

---

## 5. O que está BOM

Específico, porque deve sobreviver à refatoração:

1. **Separação de responsabilidades por módulo já aponta para portas/adaptadores.** `audio.py`, `whatsapp.py`, `teacher.py`, `limits.py` são proto-adaptadores com fronteiras certas — o comentário em `audio.py:3` ("swapping OpenAI for ElevenLabs is a one-function change") mostra a intenção correta. A refatoração formaliza essas fronteiras, não as inventa.
2. **A mentalidade de proteção de custo existe desde o dia 1.** Cap de tamanho de áudio (`audio.py:36`), rate limit por minuto, cota diária e allowlist (`limits.py`) — implementação frágil (F5), instinto certo. Raro em protótipo.
3. **Contrato estruturado com o LLM.** O `SYSTEM_PROMPT` já pede JSON com schema explícito, regras pedagógicas bem pensadas (`has_mistakes` conservador, uma dica por vez, `spoken_reply` sem markdown porque vira áudio) e há parsing tolerante a code fences (`teacher.py:72-77`). Isso é a semente do domínio `Correction` do produto futuro.
4. **Decisões de UX de produto corretas:** card só quando há correção real (`main.py:128-132`), tradução sob demanda em vez de sempre, histórico com trim. São regras de negócio a portar, não reescrever.
5. **Config fail-fast** (`config.py:8-12`): variável faltando derruba o boot com mensagem clara — espírito do `IOptions` com validação.
6. **Higiene de segredos e documentação:** `.gitignore` cobre `.env`/chaves; `README`/`SETUP`/`COMMANDS` são completos e honestos. O README documenta a stack com "why" por linha — prática que o harness agora formaliza em ADRs.
7. **Limpeza dos áudios de entrada com `try/finally`** (`main.py:116-119`) — o padrão certo, só que aplicado a metade dos arquivos (F6).

---

## 6. Veredito *(reescrito na revisão pós-ADR-0001; o original está no histórico git, commit b70b5e2)*

**Reescrever sobre nova fundação — agora com força dobrada. Portar o núcleo pedagógico; deixar o protótipo congelado como referência executável, sem investir mais nele.**

O veredito original já recomendava reescrita por argumentos de arquitetura
(esqueleto alvo incompatível, nada a proteger, aprendizado como objetivo,
núcleo portável e pequeno). O ADR-0001 adiciona o argumento decisivo, agora
**de produto**:

1. **~40% do código morre por decisão de negócio, independentemente de
   qualidade** (ver §7): toda a casca de canal — webhook, Twilio, formatação
   WhatsApp, allowlist por telefone. Refatorar incrementalmente seria polir
   código já condenado pelo próprio escopo.
2. **O que sobrevive é exatamente o que o veredito original mandava portar:**
   o núcleo pedagógico (prompt, contrato JSON, regras de produto) e os
   adapters de provider (STT/TTS). A costura está mapeada em §7 — a extração
   é viável e barata.
3. **A restrição de demonstrabilidade contínua permanece** e vira exigência do
   roadmap (P3): o protótipo WhatsApp continua executável como demo do núcleo
   pedagógico enquanto a fatia vertical do novo stack não chega à paridade.
   Muda a natureza do strangler: o protótipo não é mais um canal a manter vivo
   em produção — é uma referência de comportamento.
4. **F1/F2 deixam de merecer patch.** A recomendação original ("corrigir no
   protótipo se ficar exposto") é substituída por: **não expor o protótipo**.
   Rodá-lo apenas localmente custa zero linhas; investir segurança em código
   condenado é desperdício.

**Ressalva mantida:** a decisão de modelo (3.k) segue como ganho rápido
paralelo via `.env`, com ADR formal (Sonnet atual para resposta pedagógica,
Haiku 4.5 para auxiliares) na fase de arquitetura.

**Bloqueante novo herdado do ADR-0001:** sem allowlist, a proteção de custo
por conta (quotas, verificação de e-mail, kill switch de gasto) passa a ser
pré-requisito de qualquer lançamento — dimensionado em §7.

---

## 7. Revisão pós-mudança de escopo (P1.5 · ADR-0001 · 2026-08-17)

### 7.1 Quanto do código morre e quanto sobrevive

Base: 511 linhas em 6 módulos. Classificação linha a linha por destino:

| Categoria | Evidência | Linhas (~) | % |
|---|---|---|---|
| **Lógica de canal — morre** | `whatsapp.py` inteiro (30); `main.py` webhook/form-data/envio out-of-band (~100 de 139); `audio.py` `download_twilio_media` + `public_audio_url` (~30); `teacher.py` `format_feedback_card`/`format_translation` com markdown WhatsApp (~45 — a **estrutura** da informação sobrevive, a formatação morre); allowlist e chaves por telefone em `limits.py`/`config.py` (~15) | ~220 | **~43%** |
| **Núcleo pedagógico — preservar** | `SYSTEM_PROMPT` (teacher.py:26-48); `get_feedback` + histórico + `_trim` + `_extract_json` (teacher.py:55-121); regras de produto: card só quando há correção (main.py:128-132), tradução sob demanda, `has_corrections` | ~140 | **~27%** |
| **Neutro — portável com adaptação** | `transcribe`/`synthesize` (adapters de provider, audio.py:49-74); padrão de config fail-fast (config.py); mecânica de rate limit por janela (limits.py:21-40, rechaveada para conta) | ~150 | **~30%** |

### 7.2 Onde está a costura

O acoplamento é **fraco** — a extração do núcleo é viável sem arqueologia:

- `teacher.get_feedback(user_id, texto) → dict` não conhece Twilio, HTTP nem
  WhatsApp. É a função mais valiosa do sistema e já tem a assinatura de um
  serviço de aplicação. Contaminações: `user_id` é um telefone (`whatsapp:+55...`)
  e as funções `format_*` embutem apresentação de canal no módulo de domínio.
- `audio.transcribe`/`audio.synthesize` são adapters de provider puros — a
  fronteira de porta (trocar OpenAI sem tocar domínio) já existe informalmente.
- `main.py` é 100% casca: parsing de borda + orquestração. A orquestração
  (ordem do pipeline, quando enviar o quê) é a única lógica a resgatar dele.

**Conclusão da costura:** não é o acoplamento que justifica a reescrita — é o
fato de a casca (~43%) morrer por decisão de produto e a fundação alvo
(camadas, fila, banco, auth) não existir no protótipo. Extrai-se o núcleo por
porte de funções quase inteiras.

### 7.3 Pior cenário financeiro com cadastro aberto (24h)

A allowlist (`limits.py:18-19`) era a **única** proteção que não dependia de
bom comportamento. Sem ela:

- Custo por interação maximizada (áudio no teto de 2MB ≈ 2 min): Whisper
  $0.012 + Claude ~$0.012 + TTS ~$0.005 ≈ **$0.03/req** (Twilio sai da conta).
- Cotas por conta são contornáveis criando contas: um script com e-mails
  descartáveis a **1 req/s sustentada** gasta 86.400 × $0.03 ≈ **US$ 2.600–3.000
  em 24h**; a 10 req/s, ~US$ 30.000/24h.
- O teto real não é o atacante — é **o crédito pré-pago das contas OpenAI e
  Anthropic e seus spend limits**. Com auto-reload ligado, o teto é o cartão.

**É bloqueante para o lançamento? Sim.** Pré-requisitos mínimos antes de
qualquer beta aberto: verificação de e-mail no cadastro; quota agressiva para
conta nova (ex.: N min de áudio/dia); rate limit por conta **e** por IP;
**limite global de gasto diário com kill switch** (o serviço para de aceitar
áudio quando o orçamento do dia acaba — degradação honesta); alertas de gasto
nos dois providers; auto-reload desligado. Nada disso existe hoje.

### 7.4 Decisões que só faziam sentido no WhatsApp — erro carregar adiante

| Decisão do protótipo | Por que existia | O que fazer no destino |
|---|---|---|
| Resposta = MP3 completo em URL pública (`audio.py:77-78`) | WhatsApp só entrega mídia por URL | Streaming/playback progressivo no app; qualquer URL de mídia é assinada e expira |
| Interação estritamente turn-based, sem sessão explícita | WhatsApp é um thread infinito de mensagens | Sessão como entidade de domínio (início/fim/duração) — base de relatórios, CEFR e revisão espaçada |
| Feedback formatado como string com markdown WhatsApp (`teacher.py:147-167`) | O canal só renderiza texto | API devolve **dados estruturados** (correções tipadas); o cliente renderiza. Formatar no servidor inverte a responsabilidade |
| Identidade = número de telefone como chave universal | Era o identificador que o canal dava | Conta de usuário com auth real; telefone vira, no máximo, atributo |
| Comandos por texto mágico ("reset", "traduzir" — `config.py:35-36`) | Único input disponível era mensagem | Ações de UI explícitas |
| `translation_pt` gerada em **toda** resposta (`teacher.py:38`) | Segundo round-trip era caro/estranho no chat | Tradução on-demand via endpoint — elimina os ~30-40% de output pago e descartado |
| Resposta out-of-band via REST após 200 vazio (`main.py:68-69`) | Modelo webhook do Twilio | Job assíncrono com status consultável/push — o cliente acompanha o progresso |
| Cap de 2MB como proxy de duração (`config.py:43`) | Servidor não conhecia a duração antes de baixar | Cliente mede e limita **duração** na captura; servidor valida ambos |

### 7.5 O que do diagnóstico original continua válido

- **Integralmente:** F3 (bloqueio do event loop — agora julgado pela UX do
  app), F5 (estado em memória — vira a motivação do banco), F7 (mutação do
  histórico pré-sucesso), F8 (timeouts/retry/circuit breaker), F9 (fallback de
  JSON indo para TTS), F12 (zero testes); **seção 4 inteira** (tradução
  .NET→Python — nada nela é específica de canal); **seção 5** (o que está bom);
  checklist d–k.
- **Válido com reenquadramento:** custo por interação de IA (~$0.023–0.028 sem
  Twilio; entra custo próprio de storage/infra/push); latência da seção 1
  (o juiz muda de "timeout do Twilio" para "usuário olhando a tela"); F6
  (MP3 públicos → vira requisito de storage com URL assinada e TTL por usuário);
  F10 (parsing de borda → resolvido por pydantic no contrato da nova API).
- **Obsoleto:** F1, F2, F4, F11 e itens b/c do checklist — marcados inline.
