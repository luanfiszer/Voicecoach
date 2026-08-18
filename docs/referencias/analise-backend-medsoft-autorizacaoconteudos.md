# Análise de referência — MEDSoft.Service.AutorizacaoConteudos (C#/.NET)

- **Data:** 2026-08-18
- **Origem:** `~/Documents/MEDGRUPO/MEDSoft.Service.AutorizacaoConteudos`
  (serviço de produção da empresa do desenvolvedor)
- **Motivação:** procurar padrões de infraestrutura e performance aproveitáveis,
  com foco declarado no incômodo com o tempo de resposta de 5–10s do produto.
- **Análise irmã:** o monorepo front-end MEDSoft foi analisado no CARD-001 e o
  resultado está no [ADR-0012](../adr/0012-regra-de-camada-como-contrato-executavel.md)
  e na observação de campo do [ADR-0002](../adr/0002-stack-de-cliente-expo-mais-web-separada.md).

## O que foi lido

`README.md` (26 KB), `DeveloperHandbook.md`, `docs/devops/{api,worker,redis,database,database-migrations,checklist}.md`,
`performance/k6/*`, `src/Modules/.../Services/Cache/CacheStoreResilienceExtensions.cs`,
`src/Core/.../Consts/CacheKeys.cs`, estrutura de projetos da solution.

Arquitetura de lá, resumida: 8 projetos (`Domain`, `Data`, `Application`,
`Service`, `Presentations`, `Common`, `DependencyInjection`, `UI`), três
entrypoints (`API`, `Worker` de RabbitMQ, `RecalcularTurmaWorker` agendado),
Postgres + Redis + RabbitMQ, padrões Inbox/Outbox, k6 como gate de performance.

---

## Enquadramento honesto: por que ele não resolve nossa latência

**O gargalo dos dois sistemas não é o mesmo, e isso precisa ficar dito antes de
qualquer recomendação.**

| | AutorizacaoConteudos | Voicecoach |
|---|---|---|
| Onde o tempo vai | consulta a banco, serialização, rede | **inferência de modelo** (STT, LLM, TTS) |
| Alvo de p95 | ~200 ms | 6 s (texto) / 12–15 s (áudio) |
| Cache resolve? | sim — a resposta é determinística e reutilizável | quase não — cada áudio do aluno é novo |

Nenhum padrão de um serviço CRUD torna a inferência mais rápida. O que esse
projeto oferece de verdade é a **disciplina em volta**: como medir, como
transformar orçamento de latência em gate, como não pagar custos evitáveis
(cold start, cache derrubando request, tempo morto de polling). Isso é bastante
— mas não é o mesmo que "esse projeto vai consertar os 5–10s".

---

## Padrões aproveitáveis

### 1. Orçamento de latência como gate executável (`performance/k6/`)

Lá: catálogo de endpoints declarando `p95` por rota, com threshold que **falha o
build**, mais rodadas de *warmup* antes de medir.

```js
options.thresholds[`http_req_duration{endpoint:${ep.name}}`] = [`p(95)<${ep.p95}`];
options.thresholds[`http_req_failed{endpoint:${ep.name}}`]   = ['rate<0.01'];
```

Aqui: nosso orçamento de latência (visão §D — texto ≤ ~6 s, áudio ≤ ~12–15 s
p50) hoje é **prosa**. É exatamente a situação que o ADR-0012 corrigiu para a
regra de camada: enquanto for prosa, ninguém percebe a regressão no dia em que
ela acontece. O mesmo movimento se aplica aqui.

k6 é open source e roda local — compatível com o ADR-0010.

> **Ressalva honesta, e ela é a metade mais útil do achado:** o catálogo deles
> tem **um único endpoint ativo** (`/api/v1/sobre`, p95 200 ms), com um TODO
> admitindo que o catálogo anterior era cópia de outro serviço e batia em rotas
> inexistentes. O mecanismo está certo; a cobertura é teatro. A lição dupla é:
> montar o gate **e** garantir que ele meça o caminho que dói — no nosso caso, o
> ciclo completo do Turn, não o `/health`.

### 2. Cache é best-effort — nunca derruba a request

`CacheStoreResilienceExtensions.cs` envolve leitura e escrita de cache em
try/catch: Redis fora do ar vira `LogWarning` + consulta à fonte de verdade, não
erro 500.

```csharp
catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested) { throw; }
catch (Exception exception) { logger?.LogWarning(...); return default; }
```

Repare no detalhe fino: cancelamento é **re-lançado** antes do catch genérico.
Engolir cancelamento junto com falha de infra é um bug clássico em C#.

> **Idioma Python, sem paralelo em C#:** aqui esse cuidado é de graça.
> `asyncio.CancelledError` herda de `BaseException`, não de `Exception` — então
> um `except Exception:` **já não captura** cancelamento. A linguagem faz o que
> lá exige um `when` explícito. O erro equivalente em Python é escrever
> `except BaseException:` ou um `except:` pelado.

### 3. Cachear a projeção mínima, não a entidade

Eles cacheiam `MaterialDireitoAlunoCacheModel` (5 campos) e não o view model
completo. Menos bytes no Redis, menos serialização, e o cache não quebra quando
o formato de resposta muda.

### 4. Cache-aside com invalidação explícita e TTL como constante de domínio

Chave `materiais-direito:aluno:{idAluno}`, TTL em constante
(`ValidadeConsolidadoEmHoras = 24`), invalidação disparada pela escrita que torna
o dado obsoleto, mais um endpoint de invalidação manual para operação.

Aqui: o único cache com retorno real no nosso fluxo é o de **TTS**. Frases do
professor se repetem (saudações, elogios, formulações recorrentes de correção);
sintetizar a mesma frase de novo é trabalho puro desperdiçado. Chave por
`hash(texto + voz + versão-do-modelo)`, áudio no storage, referência no Redis. O
STT não cacheia (todo áudio do aluno é novo) e o LLM só cacheia por prefixo de
prompt (ver §8).

### 5. Máquina de estados explícita no consumo de mensagem (Inbox)

O worker deles registra `RECEIVED` → `PROCESSING` → `PROCESSED` /
`PROCESSING_FAILED`, e distingue duas respostas ao broker:

- **`NackRequeue`** quando não conseguiu nem registrar a mensagem — falha de
  infraestrutura, vale tentar de novo;
- **`NackDrop`** quando o processamento falhou — erro determinístico, reprocessar
  produziria o mesmo erro; notifica e sai.

Aqui: nosso `Turn` já nasce com `status`, mas "processing" como estado único
esconde informação de que precisamos por dois motivos — mostrar texto antes do
áudio (visão §D) e saber **em qual etapa** o tempo foi gasto. O estado deveria
nomear a etapa (`transcribing`, `reasoning`, `synthesizing`), e a política de
retry do arq deveria distinguir falha transitória (timeout de rede → retry) de
determinística (áudio corrompido → falha registrada, sem retry).

### 6. Documentar o que **não** está pronto

Da seção "Pontos de atenção" deles:

> `OutboxMessage` ainda não publica mensagens sozinho; não assumir entrega
> transacional até o publisher Outbox existir.

Um aviso desses vale mais que três páginas de arquitetura aspiracional. É o mesmo
espírito da nossa seção de dívidas por card — e vale manter em qualquer README de
componente que pareça mais completo do que é.

---

## O que **não** trazer

- **Fragmentar em 8 projetos.** Lá a separação existe porque o `.csproj` é o que
  impõe a fronteira. Aqui o ADR-0012 já resolve isso com `import-linter` sem
  fragmentar o empacotamento — a Alternativa C daquele ADR é exatamente isso, e
  foi rejeitada por custo.
- **Inbox/Outbox completos agora.** São a resposta certa para entrega
  transacional entre serviços com múltiplos publishers. Temos um worker, um
  produtor e um usuário; adotar agora é o overengineering que a Parte F da visão
  manda cortar. **Gatilho para reavaliar:** quando um evento nosso precisar ser
  consumido por outro serviço, ou quando perda silenciosa de job aparecer em
  produção.
- **RabbitMQ.** O ADR-0005 já decidiu arq sobre Redis, e o motivo (Redis já entra
  por rate limit/idempotência; a fila não adiciona infra nova) continua válido.

---

## A parte de latência — análise própria

Os 5–10s não têm uma causa; têm uma soma. Ordenado por **impacto esperado sobre
esforço** — e o item 0 vem antes de todos por um motivo:

### 0. Medir por etapa antes de otimizar qualquer coisa

Sem `stt_ms`, `llm_ms`, `tts_ms`, `queue_wait_ms` e `upload_ms` gravados por
Turn, toda otimização abaixo é chute. O CARD-014 (`UsageEvent`) já vai gravar
custo por Turn — gravar os tempos junto é praticamente de graça e transforma
"está lento" em "o TTS é 60% do tempo". O conceito de **memória de cálculo**
deles (registrar por que uma decisão saiu daquele jeito) é o mesmo instinto.

### 1. Pipeline em vez de série — provavelmente o maior ganho estrutural

Hoje o desenho é serial: STT → LLM → TTS, cada etapa esperando a anterior
terminar. Mas o TTS não precisa do texto **inteiro**: precisa da primeira frase.
Com a resposta do LLM em streaming, a síntese da frase 1 começa enquanto o modelo
ainda escreve a frase 3.

Ilustrando com números redondos (não medidos): LLM 3 s + TTS 4 s em série = 7 s;
pipelinado, o TTS arranca em ~1 s e o total tende a `max(LLM, TTS) + ε` ≈ 4,5 s.
A visão §D já previu "síntese por sentença" como otimização seguinte — este
achado é que ela provavelmente vale mais que qualquer ajuste de modelo.

### 2. Cold start dos modelos locais

O warmup do k6 deles é um lembrete direto: a primeira requisição de um processo
frio não é representativa — e no nosso caso ela é **catastroficamente** pior,
porque `faster-whisper` e Kokoro carregam pesos na primeira chamada. Carregar os
dois no boot do worker (não sob demanda) tira segundos do primeiro Turn de cada
sessão de trabalho. Barato de fazer, fácil de esquecer.

### 3. Tempo morto de polling

`GET /v1/turns/{id}` com backoff significa que, no pior caso, o resultado fica
pronto logo depois de um poll e o app só descobre no próximo. Com backoff
crescente, esse tempo morto pode passar de 2 s — puro desperdício, invisível em
qualquer métrica de servidor. Alternativa: **SSE** (`text/event-stream`), que em
FastAPI é barato e casa perfeitamente com status por etapa; o cliente recebe
`transcribing` → `reasoning` → texto → `synthesizing` → áudio conforme acontece.
Isso muda o contrato da API, então é decisão de ADR (afeta ADR-0003/0008), não
detalhe de implementação.

### 4. Prompt caching na chamada do Claude

O prompt do professor (persona, regras de correção, formato estruturado de saída)
é grande e estável entre turns — exatamente o perfil que o cache de prefixo da
API atende. Ganho duplo: menos tokens de entrada faturados (~0,1× no trecho lido
do cache) e menos tempo até o primeiro token.

Regras que decidem se isso funciona ou vira placebo:

- é **casamento de prefixo**: qualquer byte alterado invalida tudo depois dele;
  a ordem de renderização é `tools` → `system` → `messages`;
- conteúdo volátil (timestamp, id do turn, histórico do aluno) vai **depois** do
  último breakpoint de cache, nunca antes;
- prefixo mínimo de ~1024 tokens — abaixo disso não cacheia e não avisa;
- verificação obrigatória: `usage.cache_read_input_tokens` maior que zero em
  requisições repetidas. Zero constante = existe um invalidador silencioso.

### 5. Escolha de modelo — sem mexer no que já foi decidido

Os defaults do ADR-0010 (`claude-haiku-4-5` em dev, Sonnet no modo qualidade)
continuam corretos e são também os mais rápidos da faixa. Duas notas para
sessões futuras:

- O `CLAUDE.md` ainda cita `claude-sonnet-4-20250514` como modelo do protótipo —
  string antiga; o atual da família é `claude-sonnet-5`. Corrigir quando o
  CARD-007 tocar o adapter.
- Existe um "fast mode" da API com throughput de saída maior, mas é restrito a
  Opus 5/4.8 e cobrado a preço premium (US$ 10/US$ 50 por MTok). **Não é para
  nós** — o ADR-0010 decide isso. Registrado aqui para que uma sessão futura não
  o descubra e ache que é otimização gratuita.

---

## Proposta de próximos passos

Nenhum card foi criado a partir desta análise — a lista abaixo é proposta e
aguarda decisão:

| # | Proposta | Onde encaixa |
|---|---|---|
| 1 | Gravar timings por etapa no `UsageEvent` | ampliar **CARD-014** |
| 2 | Status do Turn por etapa + política de retry distinguindo falha transitória de determinística | ampliar **CARD-009** |
| 3 | Warmup dos modelos locais no boot do worker | ampliar **CARD-006** e **CARD-008** |
| 4 | Streaming do LLM + síntese por sentença (pipeline) | **card novo**, Fase 2 |
| 5 | Cache de TTS por hash do texto | **card novo**, Fase 2 |
| 6 | Prompt caching no adapter do Claude, com verificação de `cache_read_input_tokens` | ampliar **CARD-007** |
| 7 | Gate de latência executável (k6 ou equivalente) sobre o ciclo do Turn | **card novo**, Fase 2 |
| 8 | SSE no lugar de polling | **ADR novo** (afeta ADR-0003/0008) antes de qualquer card |
