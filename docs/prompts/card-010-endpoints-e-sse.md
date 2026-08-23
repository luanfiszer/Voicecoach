# Prompt — CARD-010: os endpoints, a idempotência e o stream que fecha a fatia vertical

- **Tipo:** prompt de sessão, complemento de `/executa-card 010`
- **Escrito em:** 2026-08-23, no fechamento do CARD-009 (PR #14, `9a69ca3`)
- **Status:** não executado

> **Este prompt não substitui o `/executa-card`.** Aquele comando carrega o
> protocolo (branch, ordem de leitura, premissas antes do plano, DoD item a
> item, convenção de commit). **Rode `/executa-card 010` e leia isto junto** —
> aqui está só o que é específico deste card, a arqueologia já feita, e as
> **seis coisas que o card assume e que não existem no repositório**.

---

## 0. Antes do plano: a fila do explicador está em nove, e três são deste card

`docs/perguntas-em-aberto.md` tem **9 perguntas abertas**. Q5 e Q6 foram
dispensadas pelo desenvolvedor; as outras sete nunca tiveram desfecho.
Reapresente **estas três na abertura, antes do plano**:

| # | Pergunta | Por que é deste card |
|---|---|---|
| **Q2** | Por que `api` e `worker` são a **mesma** camada no contrato do import-linter, e que atalho concreto a seta proibida impede? | **É a primeira vez que a pergunta tem código para responder.** Até agora `api` e `worker` nunca tinham se falado; neste card a borda enfileira o que o worker consome e lê o canal que o worker publica. A tentação de `from voicecoach.worker.main import process_turn` para enfileirar "pelo objeto" é exatamente o atalho que a seta proíbe — e o CARD-009 já pagou por uma variante disso (`adapters.health -> worker.readiness`, reprovado pelo gate) |
| **Q7** | O que `Protocol` faz que dispensa um framework de mock, e **em que momento** se descobre que um fake não satisfaz a porta? | Os testes de endpoint substituem `TurnQueue`, `MediaStorage` e o canal por fakes via `dependency_overrides` — é a sétima sessão em que isso morde |
| **Q12** | Contratos do import-linter, os dois lados: `forbidden` segue **cadeias indiretas**; `layers` só enxerga o **grafo interno** | `sse-starlette` entra e precisa das listas `forbidden`. A pergunta errou duas vezes no CARD-009 e é a mais fresca da fila |

> **É a quinta sessão seguida em que o item da DoD fecha vermelho, e a proposta
> de postmortem sobre a REGRA foi feita e não respondida no CARD-009.**
> Considere abrir esta sessão cobrando essa decisão antes de qualquer pergunta
> nova — não é sobre esta sessão, é sobre o mecanismo.

---

## 1. Por que este é o próximo card

Caminho crítico: `018 → 006 → 007 → 008 → 009 → **010** → 012`.

O CARD-009 provou que o pipeline entrega o primeiro trecho em **1,56–1,61 s**
(medição §10.2). **E não há absolutamente nenhuma forma de um cliente saber
disso.** Não existe nenhuma rota além de `/health`. O produto inteiro roda e é
inalcançável.

Este card é o que transforma "o backend funciona" em "o backend é consumível" —
e é o último do backend antes de o cliente existir (CARD-011/012).

---

## 2. O que já está decidido e não se rediscute

- [**ADR-0026**](../adr/0026-entrega-progressiva-por-sse-com-polling-como-contrato-de-recuo.md)
  — SSE com os cinco eventos nomeados, `Last-Event-ID`, **e o polling preservado
  como contrato de recuo**. O item 4 é lei: *"o SSE é uma otimização de latência
  sobre um contrato que se sustenta sem ele"*. Os dois caminhos precisam **ambos**
  ser testados, ou o recuo apodrece — está escrito lá como consequência negativa.
- [**ADR-0035**](../adr/0035-canal-worker-api-por-pubsub-com-o-banco-como-fonte-da-verdade.md)
  — **escrito ontem, e é o que mais restringe você.** O canal é pub/sub, um por
  turn (`voicecoach:turn:{turn_id}`), e **o banco é a fonte da verdade**. O que
  trafega é `storage_key`, **nunca URL assinada** — assinar é seu, no momento da
  entrega. Item 4 explica por quê.
- [**ADR-0024**](../adr/0024-midia-por-trecho-chave-url-assinada-e-retencao-assimetrica.md)
  — a URL assinada viaja no evento **SSE** (o que você monta), com TTL de
  `media_url_ttl` (15 min, já em `Settings`).
- [**ADR-0023**](../adr/0023-ciclo-de-vida-do-turn-com-entrega-em-cascata.md) +
  [**ADR-0028**](../adr/0028-derivacao-da-etapa-do-turn-mora-no-dominio.md) — a
  etapa é `turn.stage`, calculada no domínio. A borda **projeta**, nunca refaz
  os `if`. E **nenhum valor novo em `TurnStatus`** (ADR-0008).
- [**ADR-0008**](../adr/0008-contrato-api-versionamento-e-tipos-gerados.md) —
  `/v1` aditivo, OpenAPI como fonte dos tipos TS. `chunks[]` é campo **aditivo**.
- [**ADR-0017**](../adr/0017-erro-de-dominio-e-excecao-result-fica-para-o-caso-de-uso.md)
  — ver §4.1: **este é o card que finalmente decide o `Result`.**

---

## 3. Arqueologia — verificada no repositório em 2026-08-23

### 3.1 Seis coisas que o card assume e que NÃO EXISTEM

| O card assume | O que se verificou | Consequência |
|---|---|---|
| Existe uma superfície `/v1` para acrescentar rotas | **`app.py` registra um router só: `health`.** Não há prefixo `/v1`, não há `routes/turns.py`, não há `routes/sessions.py` | Você cria a superfície inteira, incluindo a decisão de como o `/v1` é montado (prefixo no `include_router`? router pai?) |
| Problem Details nos handlers (RFC 9457) | **Não existe nenhum `exception_handler` no app.** O ADR-0017 promete *"traduzida na borda para Problem Details"* e **essa borda nunca foi escrita** | É trabalho real e é fronteira: o formato do erro é contrato de API (ADR-0008). Decida se vira ADR |
| A API tem pools de conexão | **`create_app()` não tem `lifespan`.** O `check_redis` abre e fecha um cliente **por chamada**; não há engine do SQLAlchemy na API, não há pool do `arq`, não há conexão de Redis para assinar o canal | **É a lacuna estrutural do card.** Um `POST` que crie engine por request, e um SSE que abra conexão de Redis por stream, funcionam no teste e derretem em uso |
| `sse-starlette` é só instalar | **Não instalado.** Dry-run: `+ sse-starlette==3.4.8`, **sem rebaixar nada** — ao contrário do `arq` (ADR-0038). Mas repare: o projeto está em **`starlette 1.6.0`**, uma major recente | Verifique compatibilidade de verdade, não pelo `pip install` verde. Um `EventSourceResponse` que não fecha no disconnect vaza conexão em silêncio |
| `UploadFile` funciona | **`python-multipart` não está instalado.** O FastAPI levanta na definição da rota se ele faltar. Dry-run limpo: `+ python-multipart==0.0.32` | Dependência nova, critério 1 de ADR acionado junto com o `sse-starlette` |
| Há autenticação de dev | **Não há nada.** Nem token fixo, nem campo em `Settings`, nem dependência de auth. Só existe `DEV_STUDENT_ID` (`00000000-...-0001`), criado por migration | O card diz "token fixo de dev". Decida se ele existe agora ou se as rotas ficam abertas com o `DEV_STUDENT_ID` implícito — e **escreva qual**, porque "aberto por enquanto" tem que ser uma decisão, não um esquecimento |

### 3.2 O estado do código, conferido

| Fato | Consequência para você |
|---|---|
| `ArqTurnQueue` recebe um `ArqRedis` **pronto** | Quem cria o pool é a composition root. `arq.create_pool()` é async ⇒ só num `lifespan` |
| `RedisTurnEvents.publish` existe; **não existe consumidor** | Você escreve o lado do `SUBSCRIBE`. `channel_for(turn_id)` já é exportado de `adapters/events/redis_turn_events.py` — **use a função, não remonte a string** |
| `wire_name()` traduz evento→nome do fio, com `assert_never` | Os cinco nomes do ADR-0026 já estão fixados em código. Se você acrescentar um evento, o `mypy` te obriga a traduzi-lo |
| `MediaStorage.presigned_get_url` está pronto e testado contra MinIO | Assinar é HMAC local (microssegundos), mas passa por executor. Um GET com 6 trechos são 6 assinaturas |
| `Turn.stage` e `Turn.delivered_partially` são `@property` | O schema pydantic **projeta**. Refazer os `if` na borda é violação do ADR-0028 |
| `Session.start_turn()` é a fábrica, e **recusa sessão encerrada** | O `POST /turns` chama isso, não constrói `Turn` na mão. O erro é `InvalidStateTransitionError` — precisa virar Problem Details |
| `Turn.__post_init__` exige `audio_duration > 0` | O card pede validação de **duração**, e a entidade já a exige. Onde a duração vem do upload é decisão sua |
| `input_key(..., extension)` precisa da extensão | Ela sai do content-type do upload. Content-type mentiroso ⇒ chave errada. O ADR-0029 diz que o decodificador lê os próprios bytes — mas a **chave** não |
| `TurnRepository` **não** tem nada de idempotência | Nem coluna, nem índice, nem método. Ver §4.1 |
| `UnitOfWork` existe como porta (ADR-0036) | Na API o dono do commit é a **borda, por request** — o docstring já diz isso. Não repita o desenho do worker |
| Suíte hoje: **216 passed, 92,31% global, núcleo 99%** | Piso: núcleo 90%, global 80% |
| `packages/api-client/` tem **só um README** | O job `openapi` do CI é placeholder declarado: *"a geração de tipos entra quando existir rota /v1 — CARD-010"*. **É você.** |

### 3.3 O que o CARD-009 deixou pronto e que muda o card

1. **O canal existe e o formato está fixado.** O payload é
   `{"event": "<nome>", "data": {...}}`, JSON, e `data` é o `asdict` da
   dataclass. Você **desserializa isso**, não inventa formato.
2. **`GET /health/ready` já tem a quarta entrada `worker`.** Não a implemente de
   novo.
3. **O evento `feedback` NÃO é reconstituível do banco** (correções são
   CARD-013). Isso tem consequência direta e desagradável na retomada — §4.2.
4. **O `Result` tem gatilho conferido e negado no CARD-009**, com um dos três
   candidatos escritos sendo exatamente `Idempotency-Key` repetida. §4.1.

---

## 4. As armadilhas — o que o texto do card não antecipa

### 4.1 O `Result` do ADR-0017 finalmente tem dono, e é você

O ADR-0017 deixou `Result` TBD com gatilho escrito: *"o primeiro desfecho que é
normal do negócio e não bug (quota estourada, `Idempotency-Key` repetida,
convite já usado)"*. O CARD-009 conferiu e registrou que **não** era ali. Aqui é:

**`Idempotency-Key` repetida é literalmente um dos três exemplos do ADR.** E ela
não é falha: é o cliente reenviando porque a rede caiu, e a resposta correta é
`202` com o **mesmo `turn_id`**. Isso não é exceção, não é bug, e transformá-lo
em `HTTPException` seria mentir sobre o que aconteceu.

**Decida `Result` neste card, com ADR.** É a decisão mais estrutural da sessão e
a que mais custa desfazer: ela define a assinatura de **todo caso de uso futuro**.
Perguntas que o ADR tem de responder, e que ninguém respondeu ainda:

- `Result[T, E]` genérico, ou um tipo por caso de uso?
- Como a borda traduz `Err` em HTTP sem um `if` gigante?
- O que acontece com os **dois** mundos convivendo — invariante violada continua
  levantando (ADR-0017 já decidiu), e agora há também retorno de falha. A regra
  de qual usar quando precisa estar escrita, ou vira caos em seis meses.
- Em .NET você usaria `OneOf`/`ErrorOr`/`FluentResults`. Em Python **não há
  padrão de ecossistema** — `returns` existe e é pesado, e a alternativa é 20
  linhas de `@dataclass`. Diga qual, e por quê.

Leve isso ao desenvolvedor **antes da primeira linha**.

### 4.2 `Last-Event-ID`: o card pede retomada e não diz de quê

O ADR-0026 item 3 exige retomada e diz que ela lê *"os trechos persistidos"*.
Mas o `id:` do SSE tem de identificar **qualquer** evento, não só trecho — e:

- `transcribed`, `completed` e `failed` são reconstituíveis do `Turn`;
- `chunk` é reconstituível de `audio_chunks[]`, com `index` como id natural;
- **`feedback` não é reconstituível de nada** (ADR-0035, consequência negativa).

Então o esquema de `id` é decisão sua, e as opções não empatam: um contador
monotônico por turn é o mais natural para `Last-Event-ID` mas **não** é derivável
do banco na reconexão; um id estruturado (`chunk:2`, `transcribed`) é derivável
mas exige que o cliente saiba ordená-lo. **É fronteira de contrato de API
(critério 2) e ADR obrigatório.** Não decida no meio da implementação.

E escreva o que acontece com o `feedback` numa reconexão: ele **se perde**, e o
aluno o vê no histórico depois. Se isso for inaceitável, a saída não é este card
— é antecipar o CARD-013.

### 4.3 A janela de idempotência que o card cita e não resolve

O card diz *"Redis `SETNX` + TTL"* e nomeia o risco: *"janela entre 'criei o
Turn' e 'enfileirei'"*. Ele não diz a saída, e há três estados de crash:

1. crash **depois do `SETNX`, antes de criar o Turn** ⇒ a chave existe e aponta
   para nada; o retry do cliente recebe... o quê?
2. crash **depois de criar, antes de enfileirar** ⇒ Turn `queued` que ninguém vai
   processar. **É exatamente o que o CARD-025 varre** — cite-o;
3. crash **depois de enfileirar, antes de responder** ⇒ o cliente reenvia e tem
   de receber o mesmo `turn_id`.

Repare que o Redis **não** é a única opção: uma coluna `idempotency_key` com
índice único no Postgres resolve os três num commit só, sem TTL, e sem uma
segunda fonte de verdade — ao custo de uma migration e de decidir quando a chave
expira. **O card assume Redis; pergunte se essa suposição sobrevive à análise.**

### 4.4 O `lifespan` que não existe é a decisão estrutural silenciosa

Sem ele você não tem onde pôr: o engine do SQLAlchemy, o pool do `arq`
(`create_pool` é async), a conexão de Redis do pub/sub, e o cliente boto3.

O sintoma de errar é o de sempre — **funciona no teste e derrete em uso**. Um
engine por request esgota o Postgres; uma conexão de Redis por stream SSE
esgota o Redis com dez alunos.

O `check_redis` de hoje abre e fecha por chamada **de propósito** (é um probe,
roda raramente). Não copie esse padrão para o caminho quente. Em .NET isso seria
o registro de singletons no `Program.cs` e o `IAsyncDisposable` do host; aqui é
um context manager async passado ao `FastAPI(lifespan=...)` — **idioma sem
paralelo direto, explique em 3 linhas.**

### 4.5 O stream que não fecha, e o proxy que buferiza

Dois modos de falha que **não dão erro**:

- **`EventSourceResponse` que ignora o disconnect** segura a corrotina, a
  conexão de Redis e um worker do uvicorn para sempre. O ADR-0026 item 5 já
  manda ter timeout (default 60 s, **em `Settings` — o campo não existe ainda**)
  e fechar em `completed`/`failed`.
- **Proxy bufferizando `text/event-stream`** entrega tudo junto no fim. O
  produto fica exatamente tão lento quanto o polling que o SSE veio substituir, e
  nada acusa. O card manda verificar no Compose e documentar — não pule.

### 4.6 O recuo tem de ser testado, ou apodrece

O ADR-0026 registrou isso como consequência negativa: *"dois caminhos de entrega
(SSE e polling) precisam **ambos** ser testados"*. O critério de aceite do card
tem a linha *"um cliente que **só** usa `GET /v1/turns/{id}`"*. **Não corte esse
teste se o card estourar** — é o único que impede o contrato de recuo de virar
ficção.

### 4.7 Não implemente o que é de outro card

**Não** grava `UsageEvent` (CARD-014), **não** aplica quota (CARD-015), **não**
persiste correções (CARD-013), **não** faz auth real (fase própria), **não**
escreve tela (CARD-011/012). E a regra de camada é executável: se
`voicecoach.worker` aparecer num import de `api/`, o escopo vazou **e o gate
reprova** — é a Q2.

---

## 5. Escopo — o que corta se estourar

O card é **M**, e a §4.1 pode torná-lo G sozinha. A regra de desempate:
**cede escopo, nunca latência.**

- **Não corte:** o `POST` com idempotência, o SSE com os cinco eventos, o
  `chunks[]` aditivo no GET, e o teste do **recuo por polling**.
- **Pode virar card próprio:** a geração de tipos TS no CI (`openapi-typescript`
  + `packages/api-client`), o `POST /v1/sessions`, e o token fixo de dev.
- **Se quebrar em dois**, o corte natural é: (A) `POST` + `GET` + idempotência +
  Problem Details + `lifespan`; (B) o SSE com retomada. A parte A é o contrato
  que se sustenta sozinho (ADR-0026, item 4) — e é justamente por isso que ela é
  a metade que **não** pode faltar.

---

## 6. Governança

1. **Item de ADR da DoD** (confira contra `docs/adr/README.md` e **cite o
   critério**, LEARNING-0003). Candidatos já visíveis:
   - **critério 2 + 5** — a forma do `Result` (§4.1). É a mais cara da sessão;
   - **critério 2** — o esquema de `id` do SSE e a retomada (§4.2);
   - **critério 2** — o formato de erro (Problem Details) como contrato de API;
   - **critério 1** — `sse-starlette` e `python-multipart` entram (e, ao
     contrário do `arq`, **não rebaixam nada** — verificado);
   - **critério 4** — se a idempotência for por coluna no Postgres, a chave é
     dado do cliente e tem retenção.
2. **Skill `voicecoach-arquitetura`:** cobre 0001–0023 e 0030–0038; **0024–0029
   seguem não destilados** (dívida herdada). Se ela contradisser um ADR, o ADR
   ganha e a skill se corrige na mesma sessão.
3. **Decisão que os ADRs não cobrem vai ao desenvolvedor ANTES da primeira linha
   de código.** Nesta sessão são pelo menos quatro: a forma do `Result` (§4.1), o
   esquema de `id` do SSE (§4.2), Redis vs. coluna para idempotência (§4.3) e o
   token de dev (§3.1).

---

## 7. Definition of Done específica deste card

Além da DoD do `CLAUDE.md`:

- [ ] **Tempo entre o worker gravar o trecho e o evento chegar < 100 ms**,
      medido — é o critério que justifica o SSE existir. Sem número, o ADR-0026
      não se paga.
- [ ] **Reconexão com `Last-Event-ID` do 2º trecho recebe do 3º em diante** — sem
      repetir e sem pular. E o que acontece com o `feedback` está **escrito**.
- [ ] **Teste do recuo:** um cliente que só faz polling completa o turn com
      `reply_audio_url` — sem tocar no SSE.
- [ ] **Mesmo `Idempotency-Key` duas vezes ⇒ mesmo `turn_id`, um Turn no banco**,
      e o desfecho modelado pela decisão da §4.1 (não por `HTTPException`).
- [ ] **Turn que falha depois de 2 trechos:** evento `failed` com
      `delivered_partially: true` e o GET ainda listando os 2 trechos.
- [ ] **Upload inválido ⇒ 422 em Problem Details**, com o mesmo formato de todos
      os outros erros da API.
- [ ] **Um schema pydantic só** alimenta o evento e o GET (negativa registrada no
      ADR-0026: se forem dois, divergem). Prove com um teste que os compara.
- [ ] **O stream fecha** no `completed`/`failed` **e** no disconnect do cliente —
      com teste, não com confiança.
- [ ] `uv run lint-imports` verde, com `sse_starlette` e `multipart` nas listas
      `forbidden` de `domain` e `application` **no mesmo commit**. Prove que o
      gate morde — o par completo, como no CARD-009.
- [ ] Cobertura: núcleo ≥ 90%, global ≥ 80%. **Está em 99% / 92,31% hoje.**
- [ ] **Gatilho do `Result` (ADR-0017) RESOLVIDO**, não só conferido — e o ADR
      escrito.
- [ ] Q2, Q7 e Q12 reapresentadas na abertura, com desfecho registrado no card.
      **Item fechado pelo agente com a própria explicação não conta**
      (LEARNING-0004) — e cobre a decisão sobre o postmortem da regra (§0).
- [ ] Card atualizado e tabela de `docs/backlog/README.md` atualizada.

---

## 8. Restrições

- **Branch própria** a partir de `main` (com o CARD-009 mergeado). `main` é
  protegida.
- Commit **nunca** leva trailer `Co-Authored-By`
  ([LEARNING-0001](../learnings/0001-commit-com-coautoria-indesejada-do-agente.md)).
- **Não pushe nem abra PR sem perguntar.** O padrão é o dos PRs #11–#14: título
  `CARD-XXX: <frase>`, e as seções *O que entra* → *a decisão do ADR* →
  *achados/divergências* → *Gates* (saída real colada) → *Dívidas registradas no
  card* → *Regra do explicador*.
- **Custo:** este card não precisa gastar dinheiro. O teste ponta a ponta pode
  usar o fake do professor; se você quiser o pipeline real, ele já existe em
  `tests/worker/test_pipeline_integracao.py` e está marcado `slow` com o custo
  declarado. **Não crie um segundo teste pago.**
- **Não antecipe o V2** (ADR-0003): SSE é unidirecional, sem WebSocket, sem
  barge-in. O ADR-0026 item 6 é explícito.
- Responda em português. O desenvolvedor é sênior em C#/.NET e **iniciante em
  Python**: ao citar biblioteca, diga qual, por que ela e não a alternativa, e o
  equivalente mental em .NET. Idioma sem paralelo em C# — **`lifespan` como
  context manager async, gerador assíncrono como corpo de resposta HTTP,
  `dependency_overrides` do FastAPI, e o `Result` que você propuser** — pare e
  explique em 3 linhas. Sem aula de injeção de dependência, CQS ou camadas.
