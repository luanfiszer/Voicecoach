# ADR-0014 — Health check: liveness separado de readiness, checado com clientes nativos e sem porta

- **Status:** aceito — **a dívida do check de MinIO foi paga** pelo [ADR-0034](0034-adapter-s3-sincrono-em-executor-e-retencao-por-tag.md) (2026-08-23): o probe HTTP virou `head_bucket` com credencial real
- **Data:** 2026-08-18
- **Complementa:** ADR-0004 (Postgres), ADR-0005 (Redis), ADR-0006 (MinIO/S3),
  ADR-0012 (contratos de camada), visão §F (anti-overengineering)
- **Critérios de obrigatoriedade** (`docs/adr/README.md`): **1 — introduz
  dependência externa** (`asyncpg`, `redis`, `httpx`, `uvicorn`) e **2 — define
  uma fronteira** (onde o check de infraestrutura mora nas camadas).

## Contexto

O CARD-002 pede `GET /health` e `GET /health/ready` "checando
Postgres/Redis/MinIO". A frase esconde três decisões que nenhum ADR anterior
cobre:

1. **Checar de verdade exige um cliente por dependência** — e escolher cliente é
   escolher dependência. Em particular, o driver de Postgres escolhido aqui é o
   que o CARD-005 vai herdar quando montar o `create_async_engine`.
2. **Onde os checks moram.** Eles fazem IO real, mas não têm caso de uso nem
   consumidor no domínio.
3. **O que significa o código HTTP** quando uma dependência está fora.

O protótipo não tinha nada disso: o único sinal de vida era o processo do
uvicorn estar de pé.

## Decisão

1. **Dois endpoints com propósitos distintos.**
   - `GET /health` (liveness): responde 200 sem tocar em dependência nenhuma.
   - `GET /health/ready` (readiness): checa as três dependências.
2. **200 apenas se as três responderem; 503 caso contrário** — com o **mesmo
   corpo** nos dois casos, nomeando quem caiu, o erro e a latência. Quem faz
   probe lê o status HTTP; quem depura lê o corpo.
3. **Clientes escolhidos:**
   - **Postgres — `asyncpg`**, com `SELECT 1`. É o driver async canônico do
     SQLAlchemy 2.0 async decidido no ADR-0004; `DATABASE_URL` guarda o dialeto
     completo (`postgresql+asyncpg://`) e o check normaliza o prefixo.
     **O CARD-005 herda esta escolha.**
   - **Redis — `redis-py` async** (`redis.asyncio`), com `PING`.
   - **MinIO — `httpx`** em `GET /minio/health/live`, não autenticado.
4. **Os checks moram em `adapters/health.py`, sem porta (`Protocol`) e sem caso
   de uso em `application`.** O router os invoca por `Depends`.
5. **Os três rodam em paralelo** (`asyncio.gather`) com timeout de 2s cada.
6. **`uvicorn` como servidor ASGI**, invocado por factory (`--factory`), pelas
   razões do ADR-0013.

### Por que o MinIO é o único checado por HTTP genérico

Validar credencial e bucket exigiria um cliente S3 (`boto3`/`aioboto3`), que
entra com a porta `MediaStorage` no CARD-008. Aqui a pergunta é "o serviço está
de pé?", não "consigo assinar uma URL?". **Dívida explícita:** quando o CARD-008
trouxer o cliente S3, este check deve virar um `head_bucket` — aí a resposta
passa a cobrir credencial e existência do bucket.

## Alternativas consideradas

### Alternativa A — Um endpoint só, sempre 200, informativo
- O que é: leitura literal do critério de aceite do card — "retorna 200 com o
  status das 3 dependências".
- Por que foi rejeitada: um readiness que responde 200 com o banco fora é
  inútil como probe — nada automatizado consegue agir sobre ele, e a informação
  fica dependendo de um humano ler JSON. O critério de aceite descreve o caminho
  feliz, que a decisão preserva. E fundir liveness com readiness é pior ainda:
  um supervisor mataria uma API sadia porque um vizinho caiu.

### Alternativa B — Check por TCP puro (`asyncio.open_connection`), zero dependência
- O que é: abrir socket no host:porta de cada serviço e fechar.
- Por que foi rejeitada: não prova que a dependência funciona, só que **alguém**
  aceita conexão naquela porta — um Postgres em recuperação, um Redis com a
  senha errada ou outro processo qualquer no 5432 passariam. Readiness que mente
  é pior que readiness ausente: cria confiança falsa. Adiaria a escolha do
  driver para o CARD-005 ao preço de um check decorativo.

### Alternativa C — `boto3`/`aioboto3` já neste card, para checar o bucket
- O que é: `head_bucket` em vez do probe HTTP.
- Por que foi rejeitada **agora**: puxa o SDK da AWS e antecipa a decisão do
  CARD-008, que é quem desenha a porta `MediaStorage` (chaves namespaced, URL
  assinada, TTL). Registrado acima como dívida com gatilho explícito.

### Alternativa D — Porta `HealthCheck` em `application/ports/` com adapters por dependência
- O que é: tratar o check como qualquer outra integração, atrás de `Protocol`,
  com um caso de uso orquestrando.
- Por que foi rejeitada: porta existe para permitir trocar provider **sem tocar
  o domínio** — e nenhum domínio consome readiness. Seria uma indireção com um
  único implementador para sempre, servindo um endpoint de infraestrutura. É
  literalmente o padrão que a visão §F manda cortar. **Gatilho para reavaliar:**
  se um caso de uso de negócio passar a depender do estado das dependências
  (ex.: degradação intencional de funcionalidade), aí a porta se justifica.

### Alternativa E — `psycopg[binary]` (psycopg3) em vez de `asyncpg`
- O que é: o driver mantido pela comunidade Postgres, também async.
- Por que foi rejeitada: é escolha defensável, mas `asyncpg` é o par canônico do
  SQLAlchemy async (mais rápido em benchmark e o dialeto mais documentado para
  esse modo). Como o CARD-005 herda a decisão, vale escolher o caminho com mais
  material e menos surpresa. **Gatilho para reavaliar:** necessidade de
  `COPY`/pipeline ou de compatibilidade com código psycopg2 legado.

## Consequências

**Positivas**
- Readiness responde uma pergunta operacional real e acionável por orquestrador.
- Falha de uma dependência é diagnosticável pelo corpo da resposta (qual, qual
  erro, quanto demorou), sem abrir log.
- `asyncio.gather` mantém a latência do endpoint no pior check, não na soma.
- Os endpoints são testáveis sem container, via `app.dependency_overrides` — o
  teste de integração com serviços reais fica para o CARD-003 (testcontainers).

**Negativas — o preço aceito**
- Quatro dependências novas, todas adicionadas às listas `forbidden` do
  import-linter no mesmo commit (regra do ADR-0012).
- O check do MinIO é o mais fraco dos três (não valida credencial nem bucket) —
  dívida com gatilho no CARD-008.
- Ter `asyncpg` no projeto antes do CARD-005 significa que a decisão de driver
  foi tomada por um endpoint de saúde. Assumido conscientemente e registrado
  aqui, em vez de descoberto depois no `create_async_engine`.
- Cada readiness abre e fecha conexão (não há pool ainda). Correto enquanto o
  endpoint é chamado por humano e por probe esporádico; quando o pool do
  SQLAlchemy existir (CARD-005), o check deve usá-lo em vez de conectar do zero.

**Equivalente mental .NET:** `AddHealthChecks()` com `/healthz` (liveness) e
`/readyz` (readiness) mapeados com predicados diferentes, e `IHealthCheck` por
dependência. A diferença é que aqui não há registro em container: a "tag" que
separa liveness de readiness é simplesmente qual função a rota chama.
