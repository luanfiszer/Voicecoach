# CARD-002 — Docker Compose de dev, configuração tipada e health check

- **ID:** CARD-002 · **Épico:** Fase 0 — Fundação
- **Plataforma:** infra/backend · **Esforço:** M · **Status:** concluído (2026-08-18)
- **Dependências:** CARD-001

## Contexto

ADR-0004/0005/0006 definem Postgres, Redis e MinIO; ADR-0010 exige tudo
local a custo zero, com Jaeger em profile opcional. O protótipo validava env
vars com `_required()` — o padrão evolui para pydantic-settings (visão §D).

## Problema

Sem infra local reproduzível nem configuração tipada, cada card seguinte
começaria improvisando ambiente.

## Proposta técnica

- `docker-compose.yml`: postgres:16, redis:7, minio (+ console), jaeger sob
  `--profile observability`. Volumes nomeados, healthchecks de container.
- `Settings(BaseSettings)` em `voicecoach.config`: DATABASE_URL, REDIS_URL,
  S3_*, ANTHROPIC_API_KEY, TEACHER_MODEL/ASSISTANT_MODEL (defaults do
  ADR-0009/0010), quotas e budgets (ADR-0010). Falha no boot se faltar
  obrigatória (preserva o fail-fast do protótipo).
- App FastAPI mínimo em `api/` com `GET /health` (liveness) e
  `GET /health/ready` (checa Postgres/Redis/MinIO).
- `.env.example` completo.

## Escopo

- **In:** compose, settings tipadas, health endpoints, primeiro teste de API
  (health) com httpx.
- **Out:** modelos de banco e migrations (CARD-005); CI (CARD-003).

## Critérios de aceite

- **Dado** `docker compose up -d`, **quando** a API sobe, **então**
  `/health/ready` retorna 200 com o status das 3 dependências.
- **Dado** um `.env` sem `ANTHROPIC_API_KEY`, **quando** a API tenta subir,
  **então** falha no boot com mensagem nomeando a variável.
- **Dado** `docker compose --profile observability up`, **então** o Jaeger UI
  responde localmente.

## Riscos

Portas ocupadas na máquina; versões de imagem — fixar tags.

## Objetivo de aprendizado

pydantic-settings como `IOptions<T>` + validação de boot: onde a tipagem
acontece (import time vs runtime), como defaults/env/arquivo se compõem, e o
idioma `model_config`/`SettingsConfigDict` que não tem paralelo direto em C#.

---

## Execução (2026-08-18)

### O que foi entregue

- **`docker-compose.yml` na raiz** — postgres 16.15-alpine, redis 7.4.10-alpine,
  minio RELEASE.2025-09-07T16-13-09Z, jaeger 2.20.0 sob
  `--profile observability`. Volumes nomeados, healthcheck por serviço
  (`pg_isready`, `redis-cli ping`, `mc ready local`) e portas de host
  configuráveis (`${POSTGRES_PORT:-5432}` etc.) para o risco de porta ocupada.
- **`.env.example` na raiz** — serve aos dois consumidores (substituição do
  compose e `Settings`), com o porquê de cada bloco e link para o ADR de origem.
- **`voicecoach/config.py`** — `Settings(BaseSettings)` com `frozen=True`,
  `Decimal` para dinheiro, faixas válidas (`gt=0`) e `get_settings()` memoizado
  com `@lru_cache`.
- **App FastAPI** — `create_app()` como composition root (`api/app.py`),
  `GET /health` e `GET /health/ready` (`api/routes/health.py`), schemas do
  contrato (`api/schemas/health.py`) e providers (`api/dependencies.py`).
- **`adapters/health.py`** — checks de Postgres (`asyncpg`, `SELECT 1`), Redis
  (`redis-py`, `PING`) e MinIO (`httpx`, `/minio/health/live`), rodando em
  paralelo com `asyncio.gather`, timeout de 2s cada.
- **4 testes** em `tests/api/test_health.py` + `tests/conftest.py`, com
  `pytest-asyncio` em modo `auto` e `httpx.ASGITransport`.
- **Contratos do import-linter atualizados no mesmo commit**: as 4 dependências
  novas entraram nas listas `forbidden` de `domain` e `application`, e nasceu um
  contrato novo — *"configuração é composição: domain e application não leem
  config"*.

### Decisões que viraram ADR

Verificado contra a lista **"Quando um ADR é OBRIGATÓRIO"** de
`docs/adr/README.md` (regra do LEARNING-0003):

| ADR | Critério citado |
|---|---|
| [ADR-0013](../adr/0013-configuracao-tipada-fora-das-camadas.md) — configuração tipada fora das camadas | **2 (define ou altera uma fronteira)**: cria um módulo fora das cinco camadas e a regra que o cerca |
| [ADR-0014](../adr/0014-health-check-liveness-readiness.md) — liveness vs. readiness, clientes e onde moram | **1 (introduz dependência externa)**: `asyncpg`, `redis`, `httpx`, `uvicorn`; e **2 (fronteira)**: os checks em `adapters`, sem porta |

Quatro decisões foram levadas ao desenvolvedor **antes** da implementação, por
não estarem cobertas por nenhum ADR: onde mora `config`, se o driver de Postgres
seria escolhido agora, como checar o MinIO, e onde ficam compose e `.env`. A
quinta (semântica do 503) mudava um critério de aceite e também foi confirmada.

### Evidência dos critérios de aceite

**1. `docker compose up -d` + `/health/ready` → 200 com o status das 3
dependências.**

```
$ docker compose ps --format "table {{.Service}}\t{{.Status}}"
SERVICE    STATUS
minio      Up About a minute (healthy)
postgres   Up About a minute (healthy)
redis      Up 46 seconds (healthy)

$ curl -s -w "\nHTTP %{http_code}\n" http://localhost:8000/health/ready
{"status":"ready","checks":{"postgres":{"status":"up","latency_ms":21,"error":null},
"redis":{"status":"up","latency_ms":10,"error":null},
"minio":{"status":"up","latency_ms":7,"error":null}}}
HTTP 200
```

Verificação extra do caminho infeliz (a decisão de 503, que o card não
especificava) — `docker compose stop redis`:

```
$ curl -s -w "\nHTTP %{http_code}\n" http://localhost:8000/health/ready
{"status":"not_ready","checks":{"postgres":{"status":"up","latency_ms":22,"error":null},
"redis":{"status":"down","latency_ms":7,"error":"ConnectionError: Error 61 connecting
to localhost:6379. Connection refused."},"minio":{"status":"up","latency_ms":19,"error":null}}}
HTTP 503

$ curl -s -w "\nHTTP %{http_code}\n" http://localhost:8000/health     # liveness durante a queda
{"status":"alive"}
HTTP 200
```

O liveness continuou 200 com o Redis fora — que é exatamente o ponto de separar
os dois endpoints.

**2. `.env` sem `ANTHROPIC_API_KEY` → falha no boot nomeando a variável.**

```
$ env -u ANTHROPIC_API_KEY uv run uvicorn voicecoach.api.app:create_app --factory
  File ".../src/voicecoach/api/app.py", line 29, in create_app
    resolved = settings if settings is not None else get_settings()
  File ".../src/voicecoach/config.py", line 98, in get_settings
    return Settings()
pydantic_core._pydantic_core.ValidationError: 1 validation error for Settings
anthropic_api_key
  Field required [type=missing, input_value={}, input_type=dict]

$ echo $?
1
```

Coberto também por teste (`test_configuracao_recusa_boot_sem_anthropic_api_key`).

**3. `docker compose --profile observability up` → Jaeger UI responde.**

```
$ docker compose --profile observability up -d jaeger
 Container voicecoach-jaeger-1 Started

$ curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:16686/
HTTP 200

$ docker compose config --services                        # sem a flag
postgres
redis
minio

$ docker compose --profile observability config --services
jaeger
minio
postgres
redis
```

O profile isola de verdade: sem a flag, o Jaeger nem aparece na lista de
serviços.

**4. Testes.**

```
$ uv run pytest -v
tests/api/test_health.py::test_liveness_responde_sem_tocar_em_dependencia PASSED
tests/api/test_health.py::test_readiness_200_quando_as_tres_dependencias_respondem PASSED
tests/api/test_health.py::test_readiness_503_e_nomeia_quem_caiu PASSED
tests/api/test_health.py::test_configuracao_recusa_boot_sem_anthropic_api_key PASSED
============================== 4 passed in 0.01s ===============================
```

**5. Contratos de arquitetura — e a prova de que o gate morde.**

```
$ uv run lint-imports
Camadas apontam para dentro (domain não conhece ninguém) KEPT
domain é puro: sem framework, sem SDK, sem IO KEPT
application não conhece framework nem SDK de provider KEPT
configuração é composição: domain e application não leem config KEPT
Contracts: 4 kept, 0 broken.
```

Com duas violações injetadas de propósito (`from voicecoach.config import
get_settings` no `domain`, `import asyncpg` no `application`), depois revertidas:

```
Contracts: 1 kept, 3 broken.

voicecoach.domain is not allowed to import pydantic:
-   voicecoach.domain -> voicecoach.config (l.16)
    voicecoach.config -> pydantic (l.18)

voicecoach.application is not allowed to import asyncpg:
-   voicecoach.application -> asyncpg (l.24)

voicecoach.domain is not allowed to import voicecoach.config:
-   voicecoach.domain -> voicecoach.config (l.16)
```

O contrato pegou a violação **transitiva** — `domain` alcançando `pydantic`
*através* de `config` —, que é exatamente o buraco que o ADR-0013 existe para
fechar.

### Regra do explicador — status honesto

As 2 perguntas foram feitas (o contrato novo do import-linter; o `@lru_cache` em
`get_settings()`). O desenvolvedor respondeu **"não sei responder"**, então o
item foi fechado pelo **caminho alternativo** do CLAUDE.md — "me explique até eu
conseguir defender aquilo em entrevista" —, não pela verificação por resposta.
Mesmo desfecho do CARD-001. As duas explicações, resumidas:

1. **Proibir uma dependência ≠ proibir uma direção.** O contrato antigo
   (`domain é puro`) pergunta "existe caminho de `domain` até *pydantic*?"; o
   novo pergunta "existe caminho de `domain` até *`voicecoach.config`*?". Na
   violação injetada, o antigo quebrou **por acidente**: viu
   `domain -> config -> pydantic` e reclamou do pydantic — a proteção veio de o
   `config.py` por acaso usar um pacote proibido. Dois cenários em que só o novo
   barra: (a) o gatilho já escrito no ADR-0012 — se um ADR futuro permitir
   pydantic no `domain`, `domain -> config -> pydantic` deixa de ser violação e
   o domínio passa a ler configuração sem nenhum lint reclamar; (b) alguém
   reescreve `config.py` com `os.getenv` + `dataclass` (o padrão do protótipo),
   e aí `config` só importa stdlib — verde no contrato antigo, com o domínio
   dependendo do ambiente do processo. **A frase:** contrato de dependência é
   sobre *o que você usa* e quebra quando o alvo muda; contrato de direção é
   sobre *quem você conhece* e independe do que o alvo faça por dentro. Camada é
   uma afirmação sobre conhecimento, logo precisa do segundo. Paralelo .NET:
   `Domain.csproj` não referenciar `Infrastructure.csproj` é direção; um
   analyzer barrando `using Microsoft.Data.SqlClient` é dependência — se a
   Infrastructure fosse reescrita sem SqlClient, o analyzer ficaria verde e a
   referência continuaria errada.

2. **`@lru_cache` guarda o resultado, não a entrada.** `get_settings()` não tem
   argumentos, então há uma única entrada de cache, viva enquanto o processo
   viver — e o pytest roda a suíte inteira num processo só. Se os testes usassem
   `get_settings()`: o teste A popularia o cache; o teste B faria
   `monkeypatch.setenv("DATABASE_URL", ...)` e receberia **o objeto do teste A**.
   O monkeypatch funciona (a variável muda de verdade), mas ninguém vai lê-la de
   novo: `Settings()` lê o ambiente no instante da construção e o objeto é um
   retrato congelado daquele instante. **Por que rodar B sozinho não pega:**
   sozinho ele é a primeira chamada, o cache está vazio, `Settings()` é
   realmente construído e lê o valor já modificado. O defeito só existe na ordem
   A→B — `pytest -k test_b` passa, `pytest` completo quebra, e a falha aponta
   para o teste inocente. Por isso a fixture injeta `create_app(settings)` em vez
   de chamar `get_settings()`: mesma razão pela qual se injeta em vez de usar
   `static`. Paralelo .NET: registrar `IOptions<Settings>` num container
   **estático** compartilhado entre testes — o xUnit isola por classe/collection,
   aqui não há isolamento nenhum porque o cache vive no módulo, e módulo
   importado é estado global do processo. Idioma Python sem paralelo em C#: um
   decorator **substitui o objeto** (o `get_settings` do módulo é o wrapper
   devolvido pelo `lru_cache`, com `.cache_clear()`/`.cache_info()` próprios),
   enquanto um atributo em C# é metadado passivo.

Foi oferecida a simplificação de remover o `@lru_cache` — hoje `create_app()` é
seu único consumidor, e a memoização só ganha valor com o segundo (o worker, no
CARD-009). O desenvolvedor optou por manter o código como está.

### Dívidas registradas

- **Check do MinIO é o mais fraco dos três**: `/minio/health/live` não valida
  credencial nem existência do bucket. **Gatilho:** CARD-008, que traz o cliente
  S3 — trocar por `head_bucket`.
- **Cada readiness abre e fecha conexão com o Postgres** (não há pool ainda).
  **Gatilho:** CARD-005, quando existir o engine do SQLAlchemy — o check deve
  passar a usar o pool.
- **`asyncpg` foi escolhido por um endpoint de saúde**, e o CARD-005 herda a
  decisão. Registrado no ADR-0014 em vez de descoberto depois.
- **Sem gate automatizado**: `pytest` e `lint-imports` rodam à mão. ruff, mypy,
  pre-commit e CI são o CARD-003. Não há cobertura mínima configurada.
- **Sem teste de integração** contra os serviços reais (testcontainers) — os
  testes usam `dependency_overrides`. A evidência de integração desta sessão foi
  manual, colada acima. **Gatilho:** CARD-003.
- **`Settings()` exige `# type: ignore[call-arg]`** — revisitar no CARD-003, com
  o plugin do pydantic para mypy.
- **Config declarada só até onde o card pediu**: `INVITE_CODE` (ADR-0010),
  `STT_PROVIDER`/`TTS_PROVIDER` (ADR-0011) e configuração de OTel entram nos seus
  cards. O `Settings` não antecipa campo sem dono.
- **Nenhum código exporta spans** para o Jaeger — o serviço está no compose, a
  instrumentação não existe.
- **A mensagem de erro do boot nomeia o campo em minúsculas**
  (`anthropic_api_key`), não a variável de ambiente (`ANTHROPIC_API_KEY`). É o
  comportamento padrão do pydantic e o mapeamento é direto; não vale um alias.
