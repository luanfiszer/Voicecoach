---
name: voicecoach-arquitetura
description: Regras de arquitetura do BACKEND do Voicecoach (Python, FastAPI + worker arq, camadas com portas/adapters) destiladas dos ADRs. Use ao decidir em que camada mora um módulo novo, se uma dependência pode entrar numa camada, o que é proibido em domain/application, como nomear uma porta, ou ao revisar arquitetura do backend. Não cobre o app Expo nem a web (ver Escopo).
---

# Arquitetura do backend — Voicecoach

Regras **destiladas dos ADRs** (`docs/adr/`) e da visão
(`docs/visao-produto-e-arquitetura-alvo.md`, Parte D). **Nenhuma regra aqui sem
fonte.** O *porquê* de cada uma, com o gatilho para reavaliá-la, está em
[REFERENCE.md](REFERENCE.md).

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
| Caso de uso que orquestra domínio + portas | `application/` (handler CQS) | visão §D |
| Interface para trocar provider (STT/LLM/TTS/storage/fila) | `application/ports/`, como `Protocol` | visão §D |
| Implementação de uma porta (SQLAlchemy, Anthropic, MinIO, arq) | `adapters/` | visão §D |
| Escolha de adapter por plataforma/config | `adapters/<capacidade>/factory.py`, resolvida **no boot**; incompatível **levanta**, nunca faz fallback | ADR-0027 |
| Áudio atravessando a porta de STT | `AudioInput(data: bytes)` — bytes codificados. Decodificar é do adapter; `numpy`/`av` não passam | ADR-0029 |
| Router, schema pydantic de request/response, auth, Problem Details | `api/` | ADR-0008 |
| Entrypoint que consome a fila | `worker/` | ADR-0005 |
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
- **Usar `Result` para invariante de domínio** — invariante violada é bug do
  chamador e levanta exceção; `Result` está reservado para falha *esperada* de
  caso de uso, e sua forma ainda é TBD (ADR-0017).
- **`api` importar `worker`, ou o contrário** — dois entrypoints do mesmo
  núcleo (ADR-0012).
- **Deixar `numpy` (ou qualquer tipo de biblioteca) atravessar uma porta.**
  `NDArray[np.float32]` é o tipo *natural* para "áudio" e por isso é o vazamento
  fácil de cometer sem querer: a porta trafega `bytes` (ADR-0029).
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
- **Erro: metade decidida (ADR-0017).** **Invariante de domínio violada levanta
  exceção** — `DomainError` como raiz, `InvalidStateTransitionError` para
  transição impossível; a borda traduz para Problem Details num lugar só.
  **`Result` para falha *esperada* de caso de uso continua TBD**, agora com
  gatilho escrito: o primeiro desfecho que é normal do negócio e não bug —
  quota estourada (CARD-015), `Idempotency-Key` repetida (CARD-010), convite já
  usado (Fase 3). Naquele card decide-se, e vira ADR ali. **Não invente antes.**

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
| api | rota via `httpx.AsyncClient` contra o app | pytest + httpx |
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
