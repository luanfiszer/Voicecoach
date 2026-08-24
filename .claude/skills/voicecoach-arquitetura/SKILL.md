---
name: voicecoach-arquitetura
description: Regras de arquitetura do BACKEND do Voicecoach (Python, FastAPI + worker arq, camadas com portas/adapters) destiladas dos ADRs. Use ao decidir em que camada mora um módulo novo, se uma dependência pode entrar numa camada, o que é proibido em domain/application, como nomear uma porta, ou ao revisar arquitetura do backend. Não cobre o app Expo nem a web (ver Escopo).
---

# Arquitetura do backend — Voicecoach

Regras **destiladas dos ADRs** (`docs/adr/`) e da visão
(`docs/visao-produto-e-arquitetura-alvo.md`, Parte D). **Nenhuma regra aqui sem
fonte.** O *porquê* de cada uma, com o gatilho para reavaliá-la, está em
[REFERENCE.md](REFERENCE.md).

> **Cobertura desta skill:** ADRs 0001–0023 e 0030–0042. Os ADRs **0024–0029**
> ainda não foram destilados aqui — consulte-os direto em `docs/adr/`. Se a skill
> contradisser um ADR, **o ADR ganha**.
>
> O produto deste projeto é o conhecimento do desenvolvedor; o código é
> subproduto (CLAUDE.md). Ao aplicar uma regra, saiba citar o ADR que a originou
> — regra sem lastro é opinião do agente disfarçada de convenção.

## Quem manda quando as fontes divergirem

| Fonte | O que é | Quando ganha |
|---|---|---|
| `backend/pyproject.toml` | **lei executável** — contratos do import-linter, ruff, mypy, cobertura | sempre. Se a skill disser outra coisa, a skill está errada |
| `docs/adr/` | a decisão, com alternativas e trade-offs | é a origem de toda regra abaixo |
| `backend/README.md` | documentação para humano (mapa, ambiente, comandos) | leitura, não arbitragem |
| **esta skill** | digest operacional: "onde ponho X", com a fonte citada | orienta; nunca contradiz as três acima |

Divergência entre a skill e o código **não se resolve afrouxando a skill em
silêncio**: ou o código está errado, ou falta um ADR novo (ADR-0012).

## Escopo

Só o **backend Python** (`backend/`). O app Expo e a web (ADR-0002) têm suas
próprias convenções — auth em `expo-secure-store` (ADR-0007), tipos gerados do
OpenAPI (ADR-0008) — e ganham skill própria no CARD-011, quando existir código
de cliente para conferir a regra contra ele.

## O que o produto é (a régua contra overengineering)

Tutor de inglês por **conversa de áudio**, com **correções persistidas** e
progresso. Backend = **1 API + 1 worker** sobre Postgres/Redis/MinIO, tudo local
a custo zero (ADR-0010). **V1 é turn-based** (upload + polling), desenhado para o
V2 realtime sem reescrita (ADR-0003). Não é plataforma, não é microserviço.
Antes de propor qualquer peça nova, cheque a tabela de gatilhos da **Parte F da
visão** — o corte já foi decidido, com o gatilho objetivo que o reabre.

## Mapa de camadas

```
api | worker      ← entrypoints (composition root). FastAPI / arq.
   │                api e worker NÃO se importam: são irmãos, não uma pilha
   └── adapters   ← implementam as portas: repos SQLAlchemy, STT/LLM/TTS,
        │           storage S3, fila, redis
        └── application  ← casos de uso (handlers CQS), PORTAS (Protocol)
             └── domain  ← entidades, value objects, regras puras.
                           NÃO conhece ninguém

voicecoach/config.py  ← fora das cinco camadas. Só api/worker/adapters leem
                        (ADR-0013)
```

**Tudo aponta para dentro. Uma seta que sobe é bug de arquitetura, não questão
de gosto.** E a regra é **executável**: `uv run lint-imports` (ADR-0012). Em C# a
barreira é o `.csproj`; em Python não existe fronteira de compilação, então a
fronteira é um lint.

## Onde colocar o quê

| Preciso de… | Vai em | Fonte |
|---|---|---|
| Entidade / value object / regra pura | `domain/` — só stdlib, `dataclasses` no lugar de pydantic | ADR-0012 |
| Caso de uso que orquestra domínio + portas | `application/use_cases/<comando>.py` — um handler, um comando, CQS sem MediatR. Recebe as portas por parâmetro nomeado; quem monta é a composition root | visão §D, ADR-0037 |
| Interface para trocar provider (STT/LLM/TTS/storage/fila) | `application/ports/`, como `Protocol` | visão §D |
| Implementação de uma porta (SQLAlchemy, Anthropic, MinIO, arq) | `adapters/` | visão §D |
| Escolha de adapter por plataforma/config | `adapters/<capacidade>/factory.py`, resolvida **no boot**; incompatível **levanta**, nunca faz fallback | ADR-0027 |
| Áudio atravessando a porta de STT | `AudioInput(data: bytes)` — bytes codificados. Decodificar é do adapter; `numpy`/`av` não passam | ADR-0029 |
| Áudio saindo da porta de TTS | `SynthesizedAudio(pcm: bytes, sample_rate: int)` — PCM16 mono cru, com a taxa junto porque ela é do **modelo** (Piper 22.050, Kokoro 24.000). Comprimir é de quem grava; `duration_seconds` é `@property` derivada | ADR-0033 |
| Motor de voz | **Piper** (`piper-tts`), decidido por medição. Kokoro está no enum e **levanta na subida** — não existe adapter pela metade | ADR-0032 |
| Chave de objeto no storage | `domain/media_keys.py` — o zero-padding `{index:03d}` é regra de produto (a ordem do bucket É a de playback), e a **classe de retenção é derivada da chave**, nunca parâmetro | ADR-0024, ADR-0034 |
| SDK síncrono (boto3) dentro de corrotina | `run_in_executor` — **e o motivo NÃO é o do STT**: lá é CPU-bound que solta o GIL, aqui é uma chamada síncrona que nunca cede o controle. Medido: 122 ms de event loop congelado | ADR-0034 |
| Resposta do professor atravessando a porta | **fluxo**, não objeto: `respond_streaming(history) -> AsyncIterator[TeacherEvent]`, união fechada `SpokenSentence \| FeedbackReady`. O método **não** é `async def` — gerador assíncrono já devolve o iterador na chamada | ADR-0031 |
| Erro de provedor que o caso de uso vai capturar | na **porta** (`application/ports/`), não no adapter — `application` não pode importar `adapters`. Herda de `RuntimeError`, nunca de `DomainError` | ADR-0031, ADR-0017 |
| Saída estruturada de LLM em streaming | *tool* com schema estrito + `eager_input_streaming: true`; parse com `jiter` e `partial_mode="trailing-strings"` | ADR-0030 |
| Prompt de LLM | arquivo versionado **dentro do pacote** (`adapters/llm/prompts/<papel>/vN.md`), lido com `importlib.resources`; sem conteúdo volátil no prefixo | ADR-0021, ADR-0030 |
| Router, schema pydantic de request/response, auth | `api/` | ADR-0008 |
| **Prefixo `/v1`** | declarado UMA vez, no router pai de `api/routes/__init__.py` — é fronteira de contrato, não pode estar espalhada por `prefix=` em cada include | ADR-0008 |
| **Formato de erro HTTP** | `api/errors.py` (exception handlers) + `api/schemas/problem.py`. **Problem Details RFC 9457, `application/problem+json`**, com `type` em URN (`urn:voicecoach:problem:...`) como chave semântica. Rota **nunca** monta `JSONResponse` de erro | ADR-0040 |
| **Pool/engine/cliente de vida longa na API** | `api/lifespan.py` — context manager async passado ao `FastAPI(lifespan=...)`. Nunca por request: um engine por request esgota o Postgres, uma conexão de Redis por stream esgota o Redis | ADR-0040, CARD-010 |
| **Composição por request** | `api/dependencies.py`: **um provider por porta**, e os handlers montados a partir deles. É o que faz o teste de rota trocar seis folhas por dublês sem tocar em infraestrutura | ADR-0012 |
| **Desfecho esperado de caso de uso** | `Result[T, E]` de `application/result.py` (`Ok`/`Err`, união fechada, `match` + `assert_never`). `E` é um tipo **por caso de uso**, declarado junto do handler | ADR-0039 |
| **`id` de evento SSE e retomada** | id **estruturado** (`transcribed`, `chunk:{index}`, `feedback`, `completed`, `failed`), recalculado do `Turn`. A ordem é uma função (`posicao`), nunca comparação de strings | ADR-0041 |
| **Idempotência de requisição** | coluna em `turns` com índice único **parcial**, nunca `SETNX` no Redis. A chave e o Turn nascem no mesmo commit | ADR-0042 |
| Entrypoint que consome a fila | `worker/` — `main.py` é a composition root e o `ctx` do arq é o "container" | ADR-0005, ADR-0038 |
| Modelo de IA no worker | carregado **uma vez** no `on_startup`, lido de `ctx["stt"]` / `ctx["tts"]`. Task **nunca** constrói — não quebra teste, só custa ~1 s por turno | ADR-0025 |
| Nome de fila, chave de Redis, qualquer string que **api e worker** compartilhem | módulo em `adapters/` que ambos importam (`queue/arq_turn_queue.py`, `readiness_keys.py`) — nunca no `worker/`, porque `adapters` não pode importar `worker` | ADR-0012, ADR-0038 |
| Evento do worker para a API | porta `TurnEvents` + pub/sub Redis, **um canal por turn**, com `storage_key` e nunca URL assinada. O canal é o caminho rápido; o **banco é a fonte da verdade** | ADR-0035 |
| Concorrência dentro de um caso de uso | `asyncio.Queue` + um consumidor só, dentro de um `TaskGroup`. **Nunca** `create_task` por item quando a ordem for invariante de domínio | ADR-0037 |
| Confirmar transação | porta `UnitOfWork`; na API é a borda, **no worker é o caso de uso**, comitando por marco — o turn não é uma transação, é uma sequência de marcos | ADR-0036 |
| Comprimir áudio antes de gravar | porta `AudioEncoder`; `to_aac` usa PyAV e **não pode** ser chamado de `application` (o `forbidden` alcança `av` pela cadeia indireta) | ADR-0036 |
| Leitura de env, segredo, budget | `config.py` (pydantic-settings) — passado **por parâmetro** ao núcleo | ADR-0013 |
| Migration | `alembic/` — `env.py` resolve a URL da config ou da injetada pelo teste; nunca do `.ini` | ADR-0004 |
| Ciclo de vida de um `Turn` | estado grosso em `domain`; o áudio da resposta é uma **sequência de trechos** (`TurnAudioChunk`); a **etapa** é propriedade calculada da entidade, e a borda só projeta | ADR-0023, ADR-0028 |
| Sinalizar invariante violada | exceção de `domain/errors.py` (`DomainError`), traduzida na borda | ADR-0017 |
| Montagem/escolha de adapter concreto | composition root (`api/app.py`, entrypoint do worker) | ADR-0012 |

## O que NÃO fazer

Cada proibição tem contrato executável ou ADR por trás.

- **`domain` importar framework, SDK ou IO.** Domain usa **só a stdlib**
  (ADR-0012). Contrato `forbidden` no `pyproject.toml`.
- **`application` importar framework ou SDK de provider** — nem FastAPI, nem
  driver de banco, nem SDK de IA (ADR-0012).
- **`domain` ou `application` importarem `voicecoach.config`.** Recebem valores
  **por parâmetro**; configuração é composição (ADR-0013), com contrato próprio
  porque `config.py` fica fora do contrato de camadas.
- **Modelo SQLAlchemy fora de `adapters/`** — persistência não vaza para o
  núcleo (ADR-0004).
- **pydantic fora da borda `api/`** — schema é contrato de API, não modelo de
  domínio (ADR-0008). Domain usa `dataclasses`.
- **Literal de modelo de IA no código** (`"claude-…"`) — sempre via
  `TEACHER_MODEL`/`ASSISTANT_MODEL` na config; trocar modelo é operação de
  configuração, não deploy (ADR-0009).
- **`float` para dinheiro** — sempre `Decimal` (ADR-0013).
- **Persistir o que se consegue derivar.** A etapa do `Turn` (`transcribing`,
  `thinking`, `speaking`), o `delivered_partially` e o "está ativa?" da `Session`
  **não** são colunas: são função dos artefatos e do `ended_at`. Dado duplicado é
  dado que sai de sincronia (ADR-0023). A ordem de avaliação da etapa é contrato
  (ADR-0023 item 4): **trecho de áudio antes de `transcript`** — na cascata o
  primeiro áudio existe antes de `reply_text` fechar.
- **Acrescentar valor à enum `TurnStatus`.** Ela é `queued → processing →
  completed | failed` e não cresce: `speaking` ali quebraria o contrato aditivo
  do ADR-0008. A granularidade fina vive em `TurnStage`, que é derivado
  (ADR-0023).
- **Calcular a etapa fora do `domain`.** `api/schemas`, o worker e o emissor de
  SSE **projetam** `turn.stage`; nenhum deles refaz os `if` (ADR-0028).
- **`DateTime` sem `timezone=True`** em coluna de tempo — a quota reseta por
  dia-calendário em fuso fixo, e isso é impossível sobre timestamp ingênuo
  (ADR-0023 + CARD-015).
- **Usar `Result` para invariante de domínio, ou exceção para desfecho esperado.**
  A forma do `Result` **está decidida** (ADR-0039, que fechou o TBD do ADR-0017).
  A pergunta que separa os dois mecanismos não é *"deu erro?"* — é **"quem chamou
  tem um bug?"**: se tem, exceção; se não tem, `Result`. Infraestrutura caída é
  exceção de porta, **não** `Err`. E **sucesso com nuance é `Ok`**:
  `Idempotency-Key` repetida devolve `Ok(TurnAccepted(..., replayed=True))`,
  porque `202` com o mesmo `turn_id` é sucesso, não falha.
- **Devolver `Result` de um gerador.** Ele não atravessa: um gerador assíncrono
  não tem retorno que o consumidor leia. Ali o desfecho continua sendo exceção,
  traduzida na borda (limitação registrada no ADR-0039).
- **Levantar erro 4xx de dentro do gerador de um stream.** Quando o primeiro byte
  sai, o código HTTP já foi enviado e o Starlette recusa o handler (*"response
  already started"*). O que pode virar 4xx é validado **na rota** (ADR-0040).
- **Devolver `AsyncIterator` de uma porta que precisa estabelecer estado antes de
  iterar.** O corpo de um gerador assíncrono não roda até o primeiro `__anext__`
  — `TurnEvents.subscribe` é **context manager** por isso: o `SUBSCRIBE` tem de
  existir antes de o caso de uso ler o banco, ou o que for publicado nessa janela
  cai no chão (ADR-0041, ADR-0035).
- **`api` importar `worker`, ou o contrário** — dois entrypoints do mesmo
  núcleo (ADR-0012). **E `adapters` importar `worker` também não**: aconteceu no
  CARD-009 (o health check lendo a chave de prontidão de `worker/readiness.py`) e
  o `lint-imports` reprovou. O que os dois processos compartilham mora em
  `adapters/`.
- **Reprocessar um turn que já entregou trecho.** O `arq` reexecuta a função
  inteira no retry e não sabe disso; a guarda é do caso de uso, olhando
  `turn.audio_chunks` no começo. Turn `completed` re-enfileirado é **no-op**, não
  erro (ADR-0037, CARD-009).
- **Assinar URL de mídia no worker.** A URL assinada é montada pela API no
  momento da entrega; o que atravessa o canal é a chave. Assinar cedo entrega URL
  já envelhecida a quem reconecta (ADR-0035).
- **Gravar objeto de mídia sem classe de retenção.** A tag é derivada da chave
  e chave fora do esquema levanta: esquecer a tag não daria erro, só faria voz de
  aluno viver para sempre (ADR-0034).
- **Expressar retenção por prefixo.** As chaves começam pelo `student_id`, então
  não existe prefixo comum por tipo de objeto — o lifecycle filtra por **tag**
  (ADR-0034).
- **Deixar `numpy` (ou qualquer tipo de biblioteca) atravessar uma porta.**
  `NDArray[np.float32]` é o tipo *natural* para "áudio" e por isso é o vazamento
  fácil de cometer sem querer: a porta trafega `bytes` (ADR-0029).
- **Validar saída de LLM com pydantic.** pydantic é contrato de API e vive na
  borda `api/` (ADR-0008). No adapter a validação é à mão — o schema já foi
  imposto pelo provedor, e são poucos campos de tipo conhecido (ADR-0030, item 4).
- **Deixar `spoken_reply` sair do primeiro lugar**, no prompt ou no
  `input_schema` da tool. É contrato de latência, verificado por teste — o modo
  de falha é silencioso: nada quebra, só a latência sobe (ADR-0022, ADR-0030).
- **Retentar depois de já ter emitido fala.** O aluno ouviria a resposta
  recomeçar. O `async with` do stream fica **dentro** do gerador e antes do
  primeiro `yield`, o que confina todo retry do SDK à zona legítima (ADR-0030).
- **Guardar o stream fora do `async with`, ou engolir `GeneratorExit`.**
  Abandonar a iteração é o que cancela a geração; desligar isso faz o produto
  pagar por tokens que ninguém vai ouvir (ADR-0031, item 6).
- **Fallback silencioso entre adapters.** Escolha explícita incompatível falha
  no boot; cair para o outro esconderia uma regressão de 2x atrás de um log
  (ADR-0027, item 3) — mesma classe de falha dos ADRs 0021 e 0022.
- **"Otimizar" o STT trocando modelo ou quantização.** `small.en`, `float32`,
  `beam_size=1` são resultado de medição, e `int8`/`base.en` foram medidos como
  **mais lentos** neste hardware. A escolha de modelo está BLOQUEADA até haver
  voz de aprendiz real (ADR-0027, item 7).
- **Adicionar dependência que não pode vazar para dentro sem pôr o módulo na
  lista `forbidden` no mesmo commit.** A lista não se atualiza sozinha: é o elo
  fraco assumido do ADR-0012, e lista desatualizada é gate que não morde.
- **`except Exception` sem justificativa** — o `BLE` do ruff exige `# noqa:
  BLE001` com o motivo ao lado (ADR-0015).
- **Peça de infra cortada na Parte F** (WebSocket no V1, RabbitMQ, cache de LLM,
  K8s, event sourcing, Prometheus) sem o gatilho objetivo atingido.

## Convenções

- **Portas nomeadas pela capacidade, sem sufixo `Port`:** `SpeechToText`,
  `TeacherLlm`, `TextToSpeech`, `MediaStorage`, `TurnQueue` (visão §D). A porta
  evolui por **extensão** — o V2 acrescenta `stream_*`, não altera o que existe
  (ADR-0003).
- **PEP 8 imposta por `ruff` (`N`):** `snake_case` para função e variável,
  `PascalCase` para classe, `UPPER_CASE` para constante de módulo. Os nomes de
  domínio são os da linguagem ubíqua da visão §A, em inglês: `Student`,
  `Session`, `Turn`, `Correction`, `UsageEvent`.
- **Config:** `get_settings()` memoizado com `@lru_cache`, consumido dentro de
  `create_app()`. Nunca `Settings()` no topo do módulo — o fail-fast é desejável
  no **boot**, não no import (ADR-0013).
- **Contrato de API evolui só aditivamente** sob `/v1`; breaking change é `/v2`
  convivendo (ADR-0008).
- **CQS leve:** handlers em `application`. Não é CQRS completo nem event
  sourcing (visão §F).
- **Suprimir aviso é decisão:** todo `# noqa: XXX` e `# type: ignore[...]` vem
  com o código específico e o motivo ao lado (ADR-0015).
- **Erro: decidido por inteiro** (ADR-0017 + ADR-0039 + ADR-0040).

  | Situação | Mecanismo |
  |---|---|
  | Invariante de agregado violada (`Turn.complete()` sem áudio) | **exceção** de `domain/errors.py` (`DomainError`) |
  | Infraestrutura não colaborou (fila fora, storage recusou) | **exceção** de porta, herdando `RuntimeError` |
  | Desfecho normal do negócio (sessão inexistente; quota — CARD-015) | **`Result`** (`Ok`/`Err`) |

  A borda traduz **tudo** para Problem Details num lugar só (`api/errors.py`), e
  o código HTTP responde *"de quem é o problema?"* — 409 para invariante (a
  requisição está certa, o **estado** é que não permite), 503 para porta, 4xx
  para o cliente.

## Quality gates (ADR-0015)

Três anéis: hook do agente a cada edição de `.py` → `pre-commit` → CI. De
`backend/`, à mão:

```bash
uv run ruff format --check src tests
uv run ruff check src tests
uv run mypy
uv run lint-imports
uv run pytest --cov --cov-fail-under=80
uv run coverage report --include="*/domain/*,*/application/*" --fail-under=90
```

Dois anéis de cobertura: **80% global** (com folga deliberada sobre o real —
ADR-0019: o anel global mede majoritariamente borda, que oscila; a régua sem
folga migrou para o núcleo) e **90% de `domain` + `application`** — a lógica mais barata de
testar e a mais cara de errar. Gate vermelho contornado com `--no-verify` não
conta como cumprido (CLAUDE.md).

## Testes por camada (visão §D)

| Camada | Como | Com o quê |
|---|---|---|
| domain | unit puro, sem IO | pytest |
| application | fakes em memória das portas — `Protocol` dispensa mock framework: um fake é uma classe com os métodos certos | pytest |
| adapters | integração contra dependência real em container; HTTP de provider interceptado | pytest + **testcontainers** (instalado no CARD-005, ADR-0018); respx *(ainda não)*. Esquema criado por `alembic upgrade head`, não `create_all()` |
| api | rota via `httpx.AsyncClient` contra o app, com as **portas** trocadas por dublês em `dependency_overrides` (o `lifespan` nem roda) | pytest + httpx |
| contrato | OpenAPI + geração de tipos no CI acusa breaking change | CI |
| qualidade pedagógica da IA | **não é teste unitário** — é o eval harness | Fase 4 (P5) |

## Antes de fechar (checklist de PR)

- [ ] `uv run lint-imports` verde — nenhuma seta proibida (ADR-0012)
- [ ] Dependência nova que não pode vazar para dentro entrou no `forbidden` do
      `pyproject.toml` **no mesmo commit** (ADR-0012)
- [ ] Nada de pydantic fora de `api/` (ADR-0008), SQLAlchemy fora de `adapters/`
      (ADR-0004), literal de modelo de IA (ADR-0009) ou `float` para dinheiro
      (ADR-0013)
- [ ] Todo `# noqa`/`# type: ignore` é específico e traz o motivo (ADR-0015)
- [ ] Decisão que cruza fronteira, dependência, custo ou segurança virou **ADR**
      — conferido contra a lista "Quando um ADR é OBRIGATÓRIO" de
      `docs/adr/README.md`, citando o critério (LEARNING-0003)
- [ ] Card em `docs/backlog/` atualizado; **regra do explicador** cumprida
      (CLAUDE.md)
- [ ] Regra desta skill que não bateu com o código virou ADR ou correção —
      **nunca afrouxada em silêncio** (ADR-0012)
