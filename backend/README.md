# backend — API Python do Voicecoach

Backend em camadas consumido pelos dois clientes (`apps/mobile`, `apps/web`).
Este README é a **fonte da regra de arquitetura** deste diretório — é o insumo
da skill de arquitetura (CARD-004).

Estado: **fatia vertical fechada** (até o CARD-010). O aluno manda áudio no
`POST /v1/sessions/{id}/turns`, o worker transcreve/pensa/fala em cascata, e o
cliente acompanha por SSE — com o `GET /v1/turns/{id}` como contrato de recuo.
Falta o cliente (CARD-011/012) e a autenticação (fase própria).

---

## Mapa de dependências

```
        ┌──────────────┐        ┌──────────────┐
        │     api      │        │    worker    │   entrypoints (irmãos,
        │  (FastAPI)   │        │    (arq)     │   não se importam)
        └──────┬───────┘        └──────┬───────┘
               │                       │
               └───────────┬───────────┘
                           ▼
                    ┌──────────────┐
                    │   adapters   │   implementam as portas
                    └──────┬───────┘
                           ▼
                    ┌──────────────┐
                    │ application  │   casos de uso + portas (Protocol)
                    └──────┬───────┘
                           ▼
                    ┌──────────────┐
                    │    domain    │   regras puras — não conhece ninguém
                    └──────────────┘
```

**A regra, em uma linha: tudo aponta para dentro.** Uma seta que suba é um bug
de arquitetura, não uma questão de gosto.

| Camada | Pode importar | Proibido | Equivalente .NET |
|---|---|---|---|
| `domain` | só a stdlib | framework, SDK, IO — **qualquer** dependência externa | `Domain` |
| `application` | `domain` | FastAPI, SQLAlchemy, SDKs de IA, Redis, S3 | `Application` |
| `adapters` | `application`, `domain`, libs externas | `api`, `worker`; regra de negócio | `Infrastructure` |
| `api` | `application`, `adapters`, `domain` | ser importada por outra camada; regra de negócio | `API` (controllers + `Program.cs`) |
| `worker` | `application`, `adapters`, `domain` | ser importada por outra camada; regra de negócio; importar `api` | host de `BackgroundService` |

`voicecoach/config.py` fica **fora das cinco camadas** (ADR-0013): configuração é
detalhe de composição. Só `api`, `worker` e `adapters` podem lê-la — `domain` e
`application` recebem valores por parâmetro, garantido por contrato próprio.

O docstring de cada `__init__.py` repete a regra da sua camada — quem abre o
arquivo lê a regra antes de escrever a primeira linha.

### A regra é executável

Prosa não impede import. Os contratos vivem em `[tool.importlinter]` no
`pyproject.toml`:

```bash
uv run lint-imports
```

> **Por que isso é necessário aqui e não em C#:** no .NET a barreira é o
> arquivo de projeto — `Domain.csproj` não referencia `Infrastructure.csproj`
> e o compilador impede o acoplamento. Em Python qualquer módulo importa
> qualquer módulo; não existe fronteira de compilação. Logo, a fronteira tem
> que ser um lint. Equivalente mental: `NetArchTest`/`ArchUnitNET`.

Os contratos `forbidden` listam apenas dependências **já instaladas**. Ao
adicionar uma dependência nova que não pode vazar para dentro (`boto3`,
`arq`), acrescente-a à lista do contrato no mesmo commit — a lista **não** se
atualiza sozinha, e é esse o elo fraco do ADR-0012.

> **Os dois contratos não são redundantes, e nenhum cobre o outro.** O `layers`
> opera sobre o grafo **interno** e reprova qualquer seta que suba, sem lista
> nenhuma, inclusive para módulos que não existiam quando ele foi escrito. O
> `forbidden` opera sobre uma **lista escrita à mão** e só enxerga o que alguém
> digitou — por isso o silêncio dele nunca é veredito. Demonstrado no CARD-006:
> `from faster_whisper import ...` dentro de `application` passou **verde** com
> os quatro contratos intactos até o módulo entrar na lista; com ele na lista, o
> mesmo código virou `BROKEN`.

O contrato transitivo funciona: com `from voicecoach.config import ...` injetado
no `domain`, o lint aponta os dois saltos —
`voicecoach.domain -> voicecoach.config (l.16)` e
`voicecoach.config -> pydantic (l.18)`.

---

## Estrutura

```
backend/
├── pyproject.toml            # manifesto + contratos de arquitetura + pytest
├── uv.lock                   # resolução determinística (commitado)
├── .python-version           # 3.12
├── alembic.ini               # a URL do banco NÃO mora aqui (ver env.py)
├── alembic/
│   ├── env.py                # async; URL vem da config ou é injetada pelo teste
│   └── versions/             # esquema inicial + seed do Student dev
├── tests/
│   ├── conftest.py           # fixtures (settings, app, client httpx)
│   ├── api/test_health.py
│   ├── domain/               # unitário puro, sem IO
│   └── adapters/             # integração com Postgres em container (ADR-0018)
└── src/
    └── voicecoach/
        ├── config.py         # Settings — fora das camadas (ADR-0013)
        ├── domain/
        │   ├── errors.py     # DomainError, InvalidStateTransitionError (ADR-0017)
        │   ├── media_keys.py # esquema de chaves e classe de retenção (ADR-0024)
        │   ├── student.py
        │   ├── session.py
        │   └── turn.py       # ciclo de vida do Turn (ADR-0016)
        ├── application/
        │   ├── ports/
        │   │   ├── repositories.py     # repositórios + UnitOfWork (ADR-0004/0036)
        │   │   ├── speech_to_text.py   # porta de STT (ADR-0027/0029)
        │   │   ├── teacher_llm.py      # porta do professor, em fluxo (ADR-0030/0031)
        │   │   ├── text_to_speech.py   # porta de TTS + concat de PCM (ADR-0033)
        │   │   ├── media_storage.py    # porta de storage (ADR-0024/0034/0036)
        │   │   ├── audio_encoder.py    # compressão antes de gravar (ADR-0036)
        │   │   ├── turn_queue.py       # enfileirar um turn (ADR-0005)
        │   │   └── turn_events.py      # canal worker→API (ADR-0035)
        │   └── use_cases/
        │       ├── process_turn.py     # A CASCATA (ADR-0037) — o pipeline inteiro
        │       ├── start_turn.py       # a borda aceita a fala (ADR-0039/0042)
        │       └── stream_turn_events.py # retomada + canal ao vivo (ADR-0041)
        │   └── result.py               # Ok/Err — desfecho esperado (ADR-0039)
        ├── adapters/
        │   ├── health.py           # checks de Postgres, Redis, MinIO e worker
        │   ├── readiness_keys.py   # a chave que api e worker compartilham
        │   ├── persistence/  # models, mappers, repositories, engine, seed,
        │   │                  # unit_of_work (traduz unicidade — ADR-0042)
        │   ├── stt/          # dois adapters de STT + fábrica (ADR-0027)
        │   ├── tts/          # Piper + fábrica + codificação AAC (ADR-0032/0033)
        │   ├── storage/      # adapter S3 e lifecycle do bucket (ADR-0034)
        │   ├── queue/        # adapter arq da porta TurnQueue (ADR-0038)
        │   ├── events/       # pub/sub Redis da porta TurnEvents (ADR-0035)
        │   └── llm/          # professor em streaming, corte por sentença,
        │                     # fábrica e prompts/teacher/v1.md (ADR-0030/0031)
        ├── api/
        │   ├── app.py        # create_app() — composition root
        │   ├── lifespan.py   # pools do processo: engine, arq, redis, S3 (CARD-010)
        │   ├── errors.py     # exception handlers → Problem Details (ADR-0040)
        │   ├── audio_intake.py # valida e MEDE o upload, em executor (ADR-0029)
        │   ├── dependencies.py # composição por request: uma porta, um provider
        │   ├── routes/       # __init__ monta o /v1; health, sessions, turns
        │   └── schemas/      # health, problem (RFC 9457), turns (UM schema)
        └── worker/
            ├── main.py       # composition root do worker: ctx, on_startup (ADR-0025)
            └── readiness.py  # a chave voicecoach:worker:ready + heartbeat
```

### O worker (ADR-0005, ADR-0025, ADR-0037)

```bash
uv run voicecoach-worker      # sobe o worker: carrega os modelos e consome a fila
```

**Ele é o processo que faz o produto acontecer**, e não é opcional: a API aceita
o turn e devolve; quem transcreve, pensa e fala é o worker.

Três coisas que não são óbvias e custam caro se esquecidas:

| | Por quê |
|---|---|
| **Os modelos carregam no `on_startup`, nunca na task** | Carregar por job custa ~1 s (STT ~1,1 s + TTS 0,43 s medidos — `docs/medicao-latencia.md` §10.1), mais da metade do orçamento de 1,8 s. As tasks **leem** `ctx["stt"]`; construir ali não quebra teste nenhum, só a latência sobe |
| **~1–2 GB residentes** | Requisito de máquina, não detalhe de execução (ADR-0025, item 5): os modelos ficam em memória mesmo com a fila vazia |
| **`voicecoach:worker:ready` com TTL** | Worker morto não apaga nada — ele morre. A chave expira sozinha, e é por isso que `GET /health/ready` consegue distinguir "subiu" de "pronto" |

A **forma** da cascata é contrato (ADR-0037): uma corrotina sintetiza, outra
grava, ligadas por uma `asyncio.Queue`. Trocar isso por `asyncio.create_task` por
sentença grava os trechos **fora de ordem** — às vezes com
`OutOfOrderAudioChunkError`, mais frequentemente em silêncio.

### A API (`/v1`) — ADR-0008, 0026, 0039, 0040, 0041, 0042

```bash
uv run uvicorn voicecoach.api.app:create_app --factory --reload
```

| Rota | O que responde |
|---|---|
| `POST /v1/sessions` | abre a conversa |
| `POST /v1/sessions/{id}/turns` | multipart + **`Idempotency-Key` obrigatória** → `202 {turn_id, replayed}` |
| `GET /v1/turns/{id}` | o turno completo, com `chunks[]` e URLs assinadas — **o contrato de recuo** |
| `GET /v1/turns/{id}/events` | `text/event-stream` com os cinco eventos, `Last-Event-ID` e prazo |

Cinco coisas que não são óbvias e custam caro se esquecidas:

| | Por quê |
|---|---|
| **Os pools vivem no `lifespan`, nunca por request** | Um engine de SQLAlchemy por request esgota o Postgres; uma conexão de Redis por stream SSE esgota o Redis com dez alunos. O `check_redis` do readiness abre e fecha por chamada **de propósito** (é probe, roda raramente) — **não copie aquele padrão para o caminho quente** |
| **A borda MEDE a duração do upload** | Ela decodifica o áudio (reusando o `decode` do STT) em vez de aceitar um número do cliente. Um campo declarado seria mentiroso por construção, e a quota do CARD-015 mediria ficção. Roda em **executor**: `decode` é síncrono e CPU-bound, e na corrotina congelaria o event loop da API inteira |
| **A idempotência é uma coluna, não uma chave no Redis** | A chave e o Turn nascem no mesmo commit, então não existe estado em que a chave aponte para nada (ADR-0042). O caminho repetido **enfileira de novo** — o `_job_id` do arq torna isso seguro, e é o que cura o crash entre gravar e publicar |
| **`Result` para desfecho esperado, exceção para invariante** | A pergunta que separa não é "deu erro?", é **"quem chamou tem um bug?"** (ADR-0039). Sessão inexistente é `Err`; sessão **encerrada** levanta, porque é invariante do agregado |
| **Erro 4xx é decidido ANTES de a resposta começar** | Num stream, o código HTTP já saiu quando o primeiro byte sai — um `exception_handler` que dispare depois é recusado pelo Starlette. Por isso o `Last-Event-ID` é validado na rota, não no gerador (ADR-0040, item 7) |

**O que a porta `TurnEvents.subscribe` compra sendo um context manager.** O corpo
de um gerador assíncrono não roda até a primeira iteração — se ela devolvesse o
iterador direto, o `SUBSCRIBE` ainda não teria acontecido quando o caso de uso
fosse ler o banco, e todo evento publicado nessa janela cairia no chão (pub/sub
não guarda nada, ADR-0035). O sintoma seria um trecho de áudio que não chega, de
forma intermitente. Com o `async with`, a ordem é garantida: **assina, depois lê**.

**Latência do canal, medida** (`tests/adapters/test_turn_events_integracao.py`,
contra Redis real, 6 trechos): **mediana 0,31 ms, pior caso 1,17 ms** — o
critério do CARD-010 é 100 ms. É esse número que paga o ADR-0026.

**Proxy que buferiza `text/event-stream`** mata a entrega progressiva **sem erro
nenhum**: o produto fica tão lento quanto o polling que o SSE veio substituir. O
`docker-compose.yml` deste repositório não tem proxy (o uvicorn é falado direto),
e o stream manda `Cache-Control: no-cache` + `X-Accel-Buffering: no` mesmo assim.

**Os tipos TypeScript saem do OpenAPI** (ADR-0008) e são **commitados**:

```bash
cd backend && uv run python -c "import json, pathlib; from voicecoach.api.app import create_app; pathlib.Path('openapi.json').write_text(json.dumps(create_app().openapi(), indent=2) + '\n')"
cd .. && pnpm --filter @voicecoach/api-client run generate
```

O CI compara com o que está no repositório: mudança de contrato vira **diff
revisável no PR**, e esquecer de regenerar vira build vermelho.

### Banco e migrations (ADR-0004)

```bash
docker compose up -d postgres    # da raiz do repositório
uv run alembic upgrade head      # cria o esquema e o Student de desenvolvimento
uv run alembic revision --autogenerate -m "descrição"
```

Equivalente mental: `dotnet ef database update` / `dotnet ef migrations add`.
Duas diferenças que mordem:

- **A URL não está no `alembic.ini`.** O `env.py` a resolve da configuração
  tipada da aplicação, ou da URL injetada programaticamente (é assim que o teste
  aponta para o container descartável). Um lugar só para a verdade.
- **O autogenerate não é confiável sozinho** — ele não derruba tipos `ENUM` no
  `downgrade`, por exemplo. Leia o arquivo gerado antes de commitar; a migration
  inicial deste projeto tem exatamente esse ajuste à mão.

Os testes de adapter sobem o **próprio** Postgres em container e aplicam
`alembic upgrade head` — logo, `pytest` completo exige Docker rodando
(ADR-0018).

---

## Ambiente

Pré-requisito: [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env                      # na RAIZ do repo; preencha ANTHROPIC_API_KEY
docker compose up -d                      # na raiz: postgres, redis, minio

cd backend
uv sync                                   # cria .venv e instala do lockfile
uv run lint-imports                       # contratos de arquitetura
uv run pytest                             # testes
uv run uvicorn voicecoach.api.app:create_app --factory --reload
```

Depois, `curl localhost:8000/health/ready` deve responder 200 com as três
dependências `up`.

### STT local (ADR-0027)

`STT_PROVIDER=auto` (default) resolve pela plataforma **no boot**: `mlx` em
Apple Silicon, `faster-whisper` no resto. Escolha explícita incompatível
**falha na subida** com mensagem nomeando a plataforma — nunca cai para o outro
adapter.

```bash
uv sync --extra mlx      # só em Apple Silicon; sem isso, o caminho mlx não existe
uv run pytest -m slow    # os testes que tocam modelo de IA de verdade
```

Dois avisos de primeira execução:

- **os pesos são baixados na primeira transcrição** (36-99 s medidos, uma vez;
  ficam no cache do Hugging Face);
- **`uv sync --extra mlx` puxa o `torch`** — o `mlx-whisper` o declara como
  dependência. São ~1,3 GB de `.venv`. O CI faz `uv sync --frozen` **sem** o
  extra e não paga isso.

Os testes marcados `slow` são **deselecionados por padrão** (`addopts`): baixam
modelo e o caminho `mlx` não existe no CI, que roda em x86. Essa assimetria de
cobertura é aceita e registrada no ADR-0027, não resolvida.

### TTS local e storage (ADR-0032, ADR-0033, ADR-0034)

O motor de voz é o **Piper**, escolhido por medição contra o Kokoro (§9 da
medição): carga 0,55 s vs. 5,66 s, RTF 0,024 vs. 0,098 e **zero dependências de
sistema**. Ele não embarca vozes — baixe a que a config aponta antes de rodar:

```bash
cd backend
uv run python -m piper.download_voices en_US-lessac-medium --download-dir voices
```

Sem isso, o adapter **falha na subida** dizendo qual arquivo falta (e o comando
que o baixa). `voices/` está no `.gitignore`: são 60 MB por voz, artefato e não
código.

O storage é S3 (MinIO local). Três coisas que valem saber:

- **o bucket é criado pelo sidecar `createbuckets` do Compose**, não pela
  aplicação — em S3 real a credencial do produto lê e escreve objetos, e nada
  além disso;
- **o `boto3` é síncrono e roda em executor.** Medido: chamado direto de uma
  corrotina, um upload de 2 MB congela o event loop por 122 ms e nenhuma outra
  corrotina roda. O motivo é diferente do executor do STT — lá é CPU-bound que
  solta o GIL, aqui é uma chamada síncrona que nunca cede o controle;
- **a retenção é uma tag por objeto**, não um prefixo: as chaves começam pelo
  `student_id`, então não existe prefixo comum que selecione "todos os inputs".

```bash
uv run pytest tests/adapters/test_s3_media_storage.py   # sobe um MinIO próprio
uv run pytest -m slow tests/adapters/test_tts_piper.py  # carrega a voz de verdade
```

> O marker `slow` significa coisas diferentes por arquivo, e a diferença importa:
> nos testes de LLM ele quer dizer **gasta dinheiro**; nos de TTS e STT, **custa
> CPU e download de modelo**. Nenhum teste deste card gasta um centavo.

### Configuração (ADR-0013)

`voicecoach.config.Settings` é a declaração única e tipada de toda a
configuração — equivalente a `IOptions<T>` com `ValidateOnStart()`. Três
detalhes que valem saber:

- **Só `ANTHROPIC_API_KEY` é obrigatória.** Os endereços de infraestrutura têm
  default apontando para o `docker-compose.yml` deste repositório: o default não
  pode estar errado, ele descreve o Compose ao lado. Segredo de provedor externo
  é o contrário — nenhum default é correto.
- **A app é servida por factory** (`--factory`). Assim `create_app()` valida a
  configuração no **boot** (falha com exit 1 nomeando o campo faltante) sem que
  um simples `import voicecoach.config` exploda.
- **O `.env` mora na raiz do repositório**, onde o docker compose o lê sozinho.
  Como o backend roda de `backend/`, o `env_file` do Settings tenta `.env` e
  depois `../.env`.

### Quality gates (ADR-0015)

Três anéis, do mais barato ao mais lento. Cada um pega o que o anterior deixou
passar — é o que substitui, aqui, a barreira que em C# o compilador dá de graça.

| Anel | Quando | O que roda |
|---|---|---|
| agente | a cada `Write`/`Edit` de `.py` (hook em `.claude/settings.json`) | `ruff format`, `ruff check --fix`, `mypy` |
| pre-commit | `git commit` | o acima + `gitleaks`, `lint-imports`, higiene de arquivo |
| CI | push em `main` e todo PR | o acima + `pytest` + cobertura (2 anéis) + OpenAPI |

Instalação do anel 2 (uma vez por clone):

```bash
cd backend && uv sync
uv run pre-commit install
```

Rodando tudo à mão, de `backend/`:

```bash
uv run ruff format --check src tests   # formatação (sem reescrever)
uv run ruff check src tests            # lint
uv run mypy                            # tipos, modo estrito
uv run lint-imports                    # contratos de camada (ADR-0012)
uv run pytest --cov --cov-fail-under=80
uv run coverage report --include="*/domain/*,*/application/*" --fail-under=90
```

**Os dois anéis de cobertura.** O global está travado em **70%** — o valor real
de hoje, sem folga, para que qualquer regressão quebre. O segundo exige **90% de
`domain` + `application`**: é a lógica mais barata de testar e a mais cara de
errar. Hoje ele passa medindo zero linhas; começa a morder quando o CARD-005
trouxer o primeiro código de domínio.

**Suprimir um aviso é uma decisão.** Todo `# noqa: XXX` e `# type: ignore[...]`
deve ser específico (com o código) e trazer o motivo ao lado. Há três `noqa:
BLE001` em `adapters/health.py`: o readiness converte falha em status e por isso
captura `Exception` de propósito.

**Segredos.** O `.gitleaks.toml` da raiz estende as regras default com duas
próprias para a chave da Anthropic — as regras de fábrica do gitleaks **não**
reconhecem `sk-ant-...`, e essa é a única credencial paga do projeto
(ADR-0010). Sem elas, o hook ficaria verde justamente no caso que importa.

### Health check (ADR-0014)

| Endpoint | Pergunta que responde | Toca em dependência? |
|---|---|---|
| `GET /health` | "o processo está vivo?" | **não** — se dependesse do banco, um supervisor mataria uma API sadia por causa de um vizinho |
| `GET /health/ready` | "posso receber tráfego?" | sim: Postgres (`SELECT 1`), Redis (`PING`), MinIO (**`head_bucket` com credencial real** — ADR-0034) e **worker** (a chave de prontidão existe? — ADR-0025) |

> `/health` e `/health/ready` ficam **fora do `/v1`** de propósito: probe de
> infraestrutura não é contrato de produto e não versiona junto com ele.

A quarta entrada não é como as outras três: elas perguntam se um serviço
responde, ela pergunta se **existe worker com os modelos carregados**. Um turn
aceito sem worker pronto fica na fila até alguém subir.

`/health/ready` responde **200 só com as quatro `up`; 503 caso contrário**, com o
mesmo corpo nos dois casos — quem faz probe lê o status HTTP, quem depura lê o
JSON (qual caiu, qual erro, quanto demorou).

### Infraestrutura local

O `docker-compose.yml` fica na **raiz** do repositório (é infra do projeto, não
do pacote Python). Portas de host configuráveis por `.env` para o caso de
5432/6379 já estarem ocupadas.

```bash
docker compose up -d                            # postgres, redis, minio + cria o bucket
docker compose --profile observability up -d    # + jaeger (UI em :16686)
docker compose down                             # para; dados sobrevivem
docker compose down -v                          # para e apaga os volumes
```

O Jaeger fica atrás de profile (ADR-0010): sobe só quando se está estudando
traces. Nenhum código exporta spans ainda.

### O que cada peça faz (para quem vem de .NET)

| Peça | O que é | Equivalente mental |
|---|---|---|
| `pyproject.toml` | manifesto do projeto: nome, versão, dependências, config das ferramentas | `.csproj` (SDK-style) + `.editorconfig` de ferramentas num arquivo só |
| `uv` | resolve, instala, cria a venv e roda comandos no ambiente | `dotnet restore` + `dotnet run` + gerência do SDK |
| `uv.lock` | versões exatas de **toda** a árvore, commitado | `packages.lock.json` do NuGet |
| `.python-version` | fixa a versão do interpretador | `global.json` (SDK pinning) |
| `uv run <cmd>` | roda no ambiente do projeto sem "ativar" nada | `dotnet <tool>` |
| `.venv/` | o ambiente isolado; não se commita | `obj/`+`bin/` com os pacotes restaurados |

**Por que `src/` layout.** Sem ele, o diretório de trabalho entra no caminho de
import e `import voicecoach` acha a pasta do código-fonte mesmo que o pacote
nunca tenha sido instalado. Isso mascara erro de empacotamento: funciona na sua
máquina, quebra no container. Com `src/`, o import só resolve porque o pacote
foi de fato instalado no ambiente — o teste roda contra o artefato, não contra
a árvore de arquivos. É o mais perto que Python chega de "referenciar o
assembly em vez do diretório".

**Por que `uv` e não `pip` + `venv`.** `pip install -r requirements.txt` não
trava a árvore transitiva: duas instalações no mesmo `requirements.txt` podem
render versões diferentes de dependências indiretas — a `.venv` do protótipo em
`english_teacher_bot/` tem exatamente esse problema. `uv` produz `uv.lock` com
a árvore inteira resolvida, gerencia o interpretador e é ordens de grandeza
mais rápido. É a diferença entre restaurar com e sem lockfile.
