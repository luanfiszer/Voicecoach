# Referência arquitetural — backend do Voicecoach

Complemento do [SKILL.md](SKILL.md). Aqui mora o **porquê** de cada regra, com o
ADR de origem e o **gatilho** que a reabre. Escrito para quem vem de .NET/DDD e é
iniciante em Python (CLAUDE.md) — por isso os equivalentes mentais.

> Regra sem fonte não entra aqui. Se o código divergir da regra, ou o código está
> errado, ou falta um ADR novo — nunca afrouxe a regra em silêncio (ADR-0012).

---

## Como esta skill não mente

Nenhum linter lê markdown: esta é a única peça do harness sem anel de
verificação automática (ADR-0015 cobre `.py`, não `.md`). Três hábitos a
substituem, e eles são a razão de o texto abaixo ser curto:

1. **Não copiar valor que muda.** A lista concreta de módulos proibidos, os
   percentuais de cobertura e a lista de dependências vivem no
   `backend/pyproject.toml`. Aqui fica a **regra**, e o ponteiro para o arquivo.
   Cópia de valor volátil é a forma mais rápida de a skill começar a mentir.
2. **Toda regra cita o ADR.** Quem discorda tem onde conferir — e onde ler a
   alternativa que foi rejeitada.
3. **A skill cresce por postmortem, não por antecipação.** O log no fim deste
   arquivo registra o que mudou e por quê. Regra que virou letra morta deve ser
   **removida**, não mantida por respeito.

**E o caminho inverso também vale:** regra da skill que o contrato ainda não
cobre é buraco no gate, não decoração da skill. Foi assim que o `pydantic`
entrou na lista `forbidden` de `application` (ver o log no fim). Ao escrever uma
regra aqui, pergunte se ela é executável — se for, ela pertence ao
`pyproject.toml`, e a skill só a explica.

---

## Por que a camada é um *contrato executável* e não prosa

Em .NET, `Domain.csproj` não referencia `Infrastructure.csproj` e o compilador
recusa o acoplamento — a arquitetura é imposta pela ferramenta. **Python não tem
essa barreira**: qualquer módulo importa qualquer módulo. A fronteira só existiria
na disciplina de quem escreve — e este projeto roda sessão a sessão, sem memória
entre elas. Regra que depende de lembrar erode.

Por isso a regra de camada vive no `pyproject.toml` como contrato do
**import-linter**, rodável com `uv run lint-imports` (**ADR-0012**). A violação
vem com arquivo e linha: `voicecoach.domain -> fastapi (l.16)`. O contrato é
transitivo: um `from voicecoach.config import ...` no `domain` acusa os dois
saltos, `domain -> config` e `config -> pydantic`.

**Equivalente mental:** `NetArchTest`/`ArchUnitNET` no build — com a diferença de
que lá são reforço opcional sobre a barreira do `.csproj`; **aqui eles são a
barreira**.

Os contratos ativos estão em `[tool.importlinter]` no `backend/pyproject.toml` —
leia lá, não aqui: são quatro, um de `layers` e três de `forbidden`
(pureza do `domain`, `application` sem framework/SDK, e núcleo sem `config`).

**Elo fraco assumido (ADR-0012, "Consequências negativas"):** os contratos
`forbidden` só listam dependências **instaladas** e **não se atualizam
sozinhos**. Ao adicionar algo que não pode vazar para dentro (`sqlalchemy`,
`anthropic`, `arq`, `boto3`…), inclua o módulo na lista **no mesmo commit** que
adiciona a dependência. A mitigação é convenção, não automação — foi decidido
assim conscientemente.

**Segundo escape conhecido:** o import-linter enxerga só imports **estáticos**.
Uma fábrica dinâmica de adapter (`importlib.import_module`) some do grafo. Por
isso escolha dinâmica de adapter mora na composition root (`api`/`worker`), onde
importar qualquer coisa já é legal.

---

## As camadas em detalhe

### `domain` — o núcleo puro

Entidades, value objects e regras que dependem só de si mesmas. **Só a
biblioteca padrão**, incluindo `dataclasses` no lugar de pydantic (ADR-0012). Os
conceitos vêm da linguagem ubíqua da visão §A: `Student`, `Session`, `Turn`,
`Correction`, `UsageEvent`, `CefrAssessment` (e, pós-MVP, `ErrorPattern`).

*`dataclass` é o gerador de boilerplate do Python: o decorador escreve
`__init__`, `__repr__` e `__eq__` a partir dos campos anotados. Equivalente
mental: um `record` de C#, mas mutável por padrão (`frozen=True` o torna
imutável) e sem validação nenhuma — validar é responsabilidade sua.*

**Por que sem pydantic:** um domínio que não depende do ciclo de release de um
framework de validação. O preço é conversão explícita entidade↔schema nas
bordas. **Gatilho para reavaliar:** se a conversão virar boilerplate em mais de
três agregados, escrever ADR — não afrouxar (ADR-0012).

### `application` — casos de uso e portas

Handlers CQS que orquestram domínio + portas. **Sem framework, sem SDK de
provider** (ADR-0012). É onde vivem as **portas**, a fronteira que permite trocar
provider sem tocar no núcleo.

Portas (visão §D), nomeadas pela capacidade:

| Porta | Assinatura essencial |
|---|---|
| `SpeechToText` | `transcribe(audio) -> Transcript` |
| `TeacherLlm` | `respond(history, student_profile) -> TeacherFeedback` |
| `TextToSpeech` | `synthesize(text) -> AudioRef` |
| `MediaStorage` | `put(...)` / `get_signed_url(ttl)` |
| `TurnQueue` | `enqueue(turn_id)` |

*`Protocol` é a interface **estrutural** do Python: quem tiver os métodos com a
assinatura certa satisfaz a porta, sem herdar nem declarar nada. Equivalente
mental: uma interface C#, só que verificada por forma (duck typing checado pelo
mypy) em vez de por declaração — o adapter não escreve `: SpeechToText`.*

Consequência prática, e ela vale ouro nos testes: um **fake em memória** é só uma
classe com os métodos certos. Nada de Moq, nada de framework de mock (visão §D).

**Evolução para o V2 (ADR-0003):** a porta ganha variante streaming por
**extensão** (`stream_transcribe`), nunca por quebra. O que atravessa o V1→V2
intacto: domínio, auth, persistência, quotas e as próprias portas. Descarte
estimado: **~15–20%** do backend (upload/polling e a variante batch dos
adapters) — número do próprio ADR-0003, que também avisa que ele cresce se as
costuras forem mal feitas.

### `adapters` — as implementações

Repositórios SQLAlchemy, clientes STT/LLM/TTS, storage S3, fila arq, redis. É a
**única** camada que conhece esses SDKs. Trocar OpenAI por ElevenLabs = novo
adapter, zero mudança acima. STT e TTS são **locais por default** em
desenvolvimento (faster-whisper, Kokoro), com as APIs pagas atrás de
configuração (ADR-0011) — consequência direta da política de custo.

### `api` — a borda HTTP

FastAPI: routers, **schemas pydantic** (o contrato, e o único lugar onde pydantic
aparece), auth, exception handlers com Problem Details. REST sob `/v1`, OpenAPI
como fonte de verdade dos tipos dos clientes (ADR-0008).

### `worker` — o consumidor da fila

Entrypoint do arq (ADR-0005). Processo **separado** da api. *Equivalente mental:
o host de um `BackgroundService` — só que como processo próprio, não uma thread
dentro da API.*

### `config.py` — composição, fora das camadas (ADR-0013)

`pydantic-settings`. Mora no topo do pacote porque configuração não é `domain`,
nem `application`, nem `adapters`, nem entrypoint — é detalhe de composição.
`domain` e `application` **recebem valores por parâmetro**; nunca importam
config, e há contrato do import-linter só para isso.

- **Só `ANTHROPIC_API_KEY` é obrigatória** (sem default): segredo de terceiro não
  tem default correto. Endereço de infra (`DATABASE_URL`, `REDIS_URL`, `S3_*`)
  tem, porque o default descreve o `docker-compose.yml` versionado ao lado.
- **Dinheiro é `Decimal`**, nunca `float`.
- `get_settings()` com `@lru_cache` (singleton preguiçoso), consumido no
  `create_app()` (a app é servida com `uvicorn --factory`). Instanciar
  `Settings()` no topo do módulo faria o *import* explodir sem `.env` — o
  fail-fast é desejável no **boot**, não no import.

*Equivalente mental: `IOptions<T>` com `ValidateOnStart()` — mas
deliberadamente mais estrito, porque o núcleo não recebe `IOptions`, recebe
valores.* **Gatilho:** caso de uso que precise de mais de três valores de config
→ criar objeto de política em `application`, não injetar config (ADR-0013).

---

## Decisões de infraestrutura, com a fonte

| Tema | Decisão | Fonte |
|---|---|---|
| Persistência | Postgres 16 + SQLAlchemy 2.0 async + Alembic; modelos só em `adapters` | ADR-0004 |
| Fila / worker | arq sobre Redis (1 produtor, 1 consumidor); worker é processo separado | ADR-0005 |
| Storage de mídia | MinIO (S3-compatível); chaves `{student_id}/{turn_id}/…`, URL assinada de TTL curto, lifecycle de expiração | ADR-0006 |
| Auth | e-mail verificado, JWT curto (~15 min) + refresh **rotativo** com detecção de reuso | ADR-0007 (ajustado por ADR-0010) |
| Contrato de API | REST `/v1` **aditivo**; breaking = `/v2` convivendo + sunset; `GET /v1/meta` informa `min_supported_app_version` | ADR-0008 |
| Modelos de IA | dois papéis (`TEACHER_MODEL`, `ASSISTANT_MODEL`), sempre por config; trocar o modelo do professor exige rodar o eval antes | ADR-0009 (ajustado por ADR-0010) |
| Política de custo | infra a dinheiro zero; gasto restrito à IA, com teto diário **e** mensal (kill switch em Redis → `503` Problem Details) | ADR-0010 |
| STT / TTS | locais por default em dev (faster-whisper, Kokoro); APIs pagas por config | ADR-0011 |
| Config tipada | pydantic-settings fora das camadas, proibida no núcleo | ADR-0013 |
| Health check | **liveness** (processo vivo, não toca dependência) separado de **readiness** (Postgres, Redis, MinIO) | ADR-0014 |
| Quality gates | três anéis: hook do agente, pre-commit, CI; dois anéis de cobertura | ADR-0015 |

### O caminho crítico: um Turn no V1

```
app grava áudio (limita DURAÇÃO na captura, não MB)
  → POST /v1/sessions/{id}/turns   (multipart + Idempotency-Key)
      api: auth → checa quota → salva áudio no storage → cria Turn(processing)
           → enfileira → 202 {turn_id}
  → worker: STT → LLM (correções estruturadas) → TTS
           → persiste Turn + Corrections + UsageEvent (custo real)
  → app: GET /v1/turns/{id}   (polling com backoff) → payload parcial por etapa
```

`Idempotency-Key` **por tentativa de envio** é o que torna seguro o retry de rede
móvel. Orçamento de latência do V1: texto visível em ≤ ~6 s, áudio completo em
≤ ~12–15 s p50 (visão §D) — é esse número que decide se o TTS precisa virar
síntese por sentença.

---

## Proteção de custo — bloqueante, não desejável (ADR-0010)

Defesa em camadas, sempre por conta e por IP (nunca por telefone: o canal morreu
no ADR-0001): cadastro por **código de convite** no MVP; quota diária em
**minutos de áudio**; rate limit por conta e por IP; `UsageEvent` por Turn com o
custo real; **kill switch** global diário e mensal em Redis; spend limit no
console da Anthropic. STT e TTS locais (ADR-0011) mantêm o gasto recorrente
restrito ao Claude.

---

## Anti-overengineering — consulte antes de propor peça nova (visão §F)

Cortados **com gatilho objetivo**. Só reabra a discussão se o gatilho foi
atingido — e, se foi, escreva o ADR.

| Cortado | Gatilho que o reabre |
|---|---|
| Kubernetes / microserviços | nunca neste projeto (não há gatilho realista) |
| RabbitMQ | múltiplos consumidores heterogêneos ou routing complexo |
| WebSocket no V1 | primeira feature de push real (V2 realtime ou notificação in-app) |
| Realtime (V2) | V1 estável + baseline de eval + uso próprio regular |
| Event sourcing / CQRS completo | auditoria regulatória (não previsto) |
| Cache de resposta de LLM | repetição medida em `usage_events` |
| GraphQL | clientes com shapes divergentes e crônicos |
| Multi-provider de LLM com fallback automático | SLA que exija failover (não existe SLA) |
| Prometheus + Grafana | tráfego real, ou necessidade de demo de SRE |

**Regra de ouro:** a menor peça que já é produto. 1 API + 1 worker + compose
resolve o MVP.

---

## Lacunas conhecidas — não invente

- **Erro / Result pattern.** Sem ADR. A visão §D cita `Result` na camada
  `application`, mas a forma em Python (exceções na borda vs. tipo `Result`
  explícito) não foi decidida. O desenvolvedor vem do Result Pattern do .NET, o
  que torna a escolha tentadora — e é justamente por isso que ela merece ADR, com
  a alternativa "exceção + exception handler" avaliada de verdade. Gatilho:
  primeiro caso de uso real (CARD-005 em diante).
- **Nome dos adapters concretos.** A visão fixa o nome das **portas** (sem
  sufixo `Port`); o padrão de nome da implementação ainda não tem decisão. Siga
  o que os CARD-006/007/008 estabelecerem — e, se eles estabelecerem, registre
  aqui.
- **Convenção de skill do cliente** (Expo/web, ADR-0002). Fora do escopo desta;
  nasce no CARD-011.

---

## Log de decisões desta skill

O que mudou aqui, quando e por quê. Alteração de regra sem linha nova nesta
tabela é alteração que ninguém vai conseguir auditar depois.

| Data | Mudança | Motivo |
|---|---|---|
| 2026-08-18 | Skill criada e revisada no CARD-004 | Codificar os ADRs 0003–0015 em regra operacional; sem ela, cada sessão dependia da memória do agente |
| 2026-08-18 | Escopo restrito ao backend; cliente adiado para o CARD-011 | Não existe código de Expo/web ainda — regra escrita antes do código nasce letra morta (visão §F) |
| 2026-08-18 | Lista literal de módulos `forbidden` removida daqui | Duplicava o `pyproject.toml`, que muda a cada card que traz dependência nova (CARD-005, 007). Ficou a regra + o ponteiro |
| 2026-08-18 | `pydantic` acrescentado ao `forbidden` de `application` no `pyproject.toml` | A skill afirmava "pydantic só na borda `api/`" (ADR-0008) e o contrato não cobria `application` — regra documentada sem gate que a sustente |
| 2026-08-18 | Seção de quality gates passou de "TBD, entra no CARD-003" para o conteúdo do ADR-0015 | O CARD-003 fechou; a skill descrevia um estado que não existia mais |
| 2026-08-18 | `pydantic` entrou na lista `forbidden` de `application` no `pyproject.toml` | A regra "pydantic só na borda `api/`" (ADR-0008) existia na skill mas **não** no contrato: `from pydantic import BaseModel` em `application` passava com o lint verde. Achado ao demonstrar a fragilidade da denylist (CARD-004) |

*Esta skill cresce pelos postmortems (`docs/learnings/`), não por antecipação.*
