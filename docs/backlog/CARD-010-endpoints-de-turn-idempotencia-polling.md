# CARD-010 — Endpoints de Turn: upload, idempotência e entrega progressiva por SSE

- **ID:** CARD-010 · **Épico:** Fase 1 — Fatia vertical em cascata
- **Plataforma:** backend · **Esforço:** M · **Status:** **concluído** (2026-08-23)
- **Dependências:** CARD-009; ADR-0026, ADR-0023, ADR-0024

## Contexto

ADR-0008 (contrato `/v1` **aditivo**, OpenAPI como fonte dos tipos) e
[ADR-0026](../adr/0026-entrega-progressiva-por-sse-com-polling-como-contrato-de-recuo.md),
que decidiu SSE para a entrega progressiva e **preservou o polling como contrato
de recuo**. Auth ainda é token fixo de dev (auth real é fase própria).

## Por que agora

O pipeline entrega o primeiro trecho em ~1,8 s e não há como o aluno saber
disso. Com polling a 500 ms, **250 ms médios de descoberta por trecho** saem do
orçamento — 18% dele, gasto em espera pura.

## Problema

O contrato precisa entregar N coisas ao longo de um turn sem quebrar o cliente
que trata o payload de forma exaustiva (restrição do ADR-0008), e sem exigir um
roundtrip por trecho para descobrir a URL do áudio.

## Proposta técnica

- **`POST /v1/sessions/{id}/turns`** — multipart + `Idempotency-Key`; valida
  content-type e **duração** (metadata, não só MB); grava o input no storage;
  cria Turn; enfileira; `202 {turn_id}`. Chave repetida ⇒ mesmo `turn_id`, sem
  reprocessar (Redis `SETNX` + TTL).
- **`GET /v1/turns/{id}/events`** — `text/event-stream` (`sse-starlette`), com
  os cinco eventos do ADR-0026 (`transcribed`, `chunk`, `feedback`, `completed`,
  `failed`). **A URL assinada do trecho vai dentro do evento** (ADR-0024): zero
  roundtrip no caminho crítico. Consome o canal Redis que o CARD-009 publica.
- **Retomada por `Last-Event-ID`**: reconectar reenvia o que faltou, lendo os
  trechos persistidos (ADR-0023). É o que faz "o app foi para background" deixar
  de ser perda de dados.
- **Timeout de stream** (default 60 s, em `Settings`) e fechamento em
  `completed`/`failed` — stream aberto para sempre é conexão vazando.
- **`GET /v1/turns/{id}` continua completo e verdadeiro**, agora com `chunks[]`
  (**campo aditivo**) e a etapa derivada do ADR-0023 — mesmo vocabulário
  (`transcribing → thinking → speaking → completed`), **nenhum valor novo na
  enum**. Cliente antigo espera `completed` e toca o áudio inteiro.
- **Um schema pydantic só** alimentando o evento e o GET — se forem dois, eles
  divergem (negativa registrada no ADR-0026).
- `POST /v1/sessions` mínimo; Problem Details (RFC 9457) nos handlers;
  `openapi-typescript` ligado de verdade no CI.

## Escopo

- **In:** os três endpoints, idempotência, SSE com retomada, `chunks[]` no GET,
  tipos gerados, testes.
- **Out:** auth real (fase própria); quotas (CARD-015); entitlement comercial
  (CARD-023); telas (CARD-011/012).

## Critérios de aceite

- **Dado** um turn em processamento, **quando** o cliente abre o stream,
  **então** recebe o primeiro evento `chunk` com URL assinada válida, e o tempo
  entre o worker gravar o trecho e o evento chegar é **< 100 ms**.
- **Dado** um cliente que reconecta com `Last-Event-ID` do 2º trecho, **então**
  recebe do 3º em diante — sem repetir e sem pular.
- **Dado** um cliente que **só** usa `GET /v1/turns/{id}`, **então** o turn
  completa corretamente com `reply_audio_url` do áudio inteiro (o recuo é
  testado, senão apodrece — ADR-0026).
- **Dado** o mesmo `Idempotency-Key` duas vezes, **então** mesmo `turn_id` e um
  único Turn no banco.
- **Dado** um turn que falha depois de 2 trechos, **então** o evento `failed`
  carrega `delivered_partially: true` e o GET continua listando os 2 trechos.
- **Dado** upload sem áudio válido, **então** 422 em Problem Details.
- **Dado** o CI, **então** `packages/api-client` tem os tipos do OpenAPI atual e
  o diff aparece no PR.

## Riscos

- **Proxy bufferizando `text/event-stream`** mata a entrega progressiva sem
  erro nenhum — só fica lento. Verificar no Compose e documentar.
- Janela de idempotência entre "criei o Turn" e "enfileirei" (ordem das
  operações + `SETNX`).
- Cada turn ativo segura um worker do uvicorn enquanto o stream vive.

## Objetivo de aprendizado

Streaming de resposta no FastAPI/Starlette (o que é um `EventSourceResponse`,
como o servidor sabe que o cliente sumiu) e multipart/`UploadFile` — o que faz o
papel de `IFormFile`; mais o desenho de idempotência com Redis: por que
`SETNX`+TTL, e o que acontece no crash entre passos.


---

## Execução (2026-08-23)

Branch `card-010-endpoints-e-sse`, a partir de `main` com o CARD-009 mergeado
(`3a68fba`).

### Abertura: a fila do explicador e o postmortem pendente

Reapresentadas antes do plano, como manda o LEARNING-0004: **Q2** (por que `api`
e `worker` são a mesma camada — primeira sessão em que os dois processos se
falam), **Q7** (`Protocol` e o momento em que um fake deixa de servir) e **Q12**
(os dois lados do import-linter, a mais fresca da fila). Reapresentada também a
**proposta de postmortem sobre a regra do explicador** em si, aberta desde o
CARD-009 e sem resposta.

**Desfecho: nenhuma das quatro foi respondida nem dispensada.** O desenvolvedor
respondeu as quatro decisões de escopo (§ abaixo) e pediu para seguir. Silêncio
não é dispensa — as quatro seguem em `docs/perguntas-em-aberto.md`. É a **sexta**
sessão seguida com o item vermelho.

### As quatro decisões levadas antes da primeira linha de código

| Decisão | Escolha | Vira |
|---|---|---|
| A forma do `Result` (§4.1 do prompt) | `Result` mínimo próprio, ~20 linhas | [ADR-0039](../adr/0039-result-minimo-para-desfecho-esperado-de-caso-de-uso.md) |
| Esquema de `id` do SSE e retomada | id **estruturado**, derivável do banco | [ADR-0041](../adr/0041-id-estruturado-do-evento-sse-e-retomada-derivada-do-banco.md) |
| Idempotência: Redis vs. coluna | **coluna no Postgres**, índice único parcial | [ADR-0042](../adr/0042-idempotencia-do-post-por-coluna-no-postgres.md) |
| Token fixo de dev | **não entra**: rotas abertas, `DEV_STUDENT_ID` implícito, decisão escrita | — |

A conferência do gatilho do `Result` produziu um achado que o ADR-0017 não
previa e que está registrado no ADR-0039: **`Idempotency-Key` repetida — um dos
três exemplos escritos do gatilho — não é falha.** A resposta certa é `202` com o
mesmo `turn_id`, que é sucesso. O gatilho disparou por outro caso
(`SessionNotFound`), e é por isso que o tipo precisa distinguir **dois sucessos**
tão bem quanto distingue sucesso de falha.

### O que entrou

**Superfície `/v1`** (não existia — o app registrava só o router de health):

| Rota | O que faz |
|---|---|
| `POST /v1/sessions` | abre a conversa (mínimo; sem ela não há onde falar) |
| `POST /v1/sessions/{id}/turns` | multipart + `Idempotency-Key` obrigatória; valida tipo, decodifica para **medir a duração**, grava o input, cria o Turn, enfileira, `202` |
| `GET /v1/turns/{id}` | o contrato de recuo, com `chunks[]` aditivo e as URLs assinadas |
| `GET /v1/turns/{id}/events` | SSE com os cinco eventos, `Last-Event-ID` e prazo |

O `/v1` é declarado **uma vez**, num router pai em `api/routes/__init__.py`: ele é
fronteira de contrato (ADR-0008) e não pode estar espalhado por um `prefix=` em
cada include.

**As seis coisas que o card assumia e não existiam** (arqueologia do prompt de
sessão, toda confirmada):

1. **superfície `/v1`** — criada;
2. **Problem Details** — não havia `exception_handler` nenhum no app. Escrito, e
   virou o [ADR-0040](../adr/0040-formato-de-erro-da-api-problem-details.md);
3. **pools de conexão** — `create_app()` não tinha `lifespan`. Criado
   (`api/lifespan.py`), com engine, pool do `arq`, conexão de pub/sub e cliente
   S3. **Era a lacuna estrutural do card**;
4. **`sse-starlette`** — instalado. Verificado que não rebaixa nada (ao contrário
   do `arq`/ADR-0038): `starlette` ficou em 1.6.0;
5. **`python-multipart`** — instalado. Descoberto que ele expõe **dois** módulos
   importáveis (`multipart` **e** `python_multipart`), e ambos entraram nas listas
   `forbidden`;
6. **autenticação de dev** — decidido que **não entra**, por escrito.

**Achado extra, não previsto pelo card:** `starlette` **faltava** nas listas
`forbidden` desde o CARD-001. `fastapi` estava lá, mas o FastAPI é uma camada
sobre o Starlette — `from starlette.responses import Response` no núcleo passava
**verde**. Lacuna pré-existente, fechada aqui e demonstrada abaixo.

### Evidência dos critérios de aceite

**1. Tempo entre o worker gravar o trecho e o evento chegar < 100 ms.** Medido
contra **Redis real** (container próprio), 6 trechos — o pior caso de uma
resposta (ADR-0023). Caminho completo: `publish` → rede → `SUBSCRIBE` → JSON →
`parse_wire` → dataclass.

```
$ uv run pytest tests/adapters/test_turn_events_integracao.py -q -s
...
latência do canal (n=6): mediana 0.31 ms | pior 1.17 ms | limite 100 ms
.
4 passed in 0.47s
```

**Duas ordens de grandeza abaixo do limite.** O que o número não inclui: a
serialização para `text/event-stream`, que são microssegundos de `json.dumps`
sobre quatro campos, sem rede. O que ele inclui é tudo que pode dar errado.

**2. Reconexão com `Last-Event-ID` do 2º trecho recebe do 3º em diante** —
`test_reconectar_com_last_event_id_do_segundo_trecho_recebe_do_terceiro`
(`[chunk:2, chunk:3, failed]`, sem repetir e sem pular) e o gêmeo no nível de
caso de uso. **E o que acontece com o `feedback` está escrito e testado:** ele
**não** volta (`test_o_historico_nao_reconstroi_feedback`), porque não é
reconstituível até o CARD-013 — dívida do ADR-0035, agora com teste como
testemunha.

**3. Teste do recuo** — `test_um_cliente_que_so_faz_polling_leva_o_turn_ate_o_fim`:
duas leituras do `GET`, o turn fechando entre elas, `reply_audio_url` do áudio
inteiro no fim. Sem tocar no SSE.

**4. Mesma `Idempotency-Key` duas vezes ⇒ mesmo `turn_id`, um Turn no banco** —
`test_a_mesma_chave_duas_vezes_devolve_o_mesmo_turn_e_um_so_no_banco` pela rota, e
o desfecho é modelado pela decisão da §4.1: `Ok(TurnAccepted(..., replayed=True))`,
não `HTTPException`. Contra Postgres real, `test_o_indice_unico_recusa_a_mesma_chave_duas_vezes`
e `test_o_unit_of_work_traduz_a_violacao_de_unicidade_para_erro_de_porta`.

**5. Turn que falha depois de 2 trechos** — `failed` com
`delivered_partially: true` **e** o `GET` ainda listando os 2 trechos, no mesmo
teste (`test_turn_que_falha_depois_de_dois_trechos_emite_failed_parcial`).

**6. Upload inválido ⇒ 422 em Problem Details** —
`test_upload_que_nao_e_audio_valido_e_422_em_problem_details`, com
`content-type: application/problem+json`. Os outros erros usam o **mesmo**
formato: 415 (tipo recusado), 413 (áudio longo), 404 (sessão/turn), 409 (sessão
encerrada), 400 (`Last-Event-ID` inválido), 503 (porta).

**7. Um schema pydantic só** — `ChunkPayload` alimenta o item de
`TurnResponse.chunks` **e** o corpo do evento `chunk`. Provado por dois testes: a
identidade da classe (`TurnResponse.model_fields["chunks"].annotation ==
list[ChunkPayload]`) e a comparação ponta a ponta dos dois payloads
(`test_o_payload_do_evento_chunk_e_identico_ao_item_do_get`).

**8. O stream fecha** nos três casos, com teste: no terminal, no prazo, e no
disconnect do cliente. Os três verificam que a **assinatura foi devolvida**
(`fakes.canal.assinantes(turn.id) == 0`), não que "provavelmente" foi.

**9. Tipos TS gerados no CI** — job `contrato OpenAPI e tipos TypeScript`, com
`openapi-typescript` e um `git diff --exit-code`: `backend/openapi.json` e
`packages/api-client/src/schema.d.ts` são commitados, então mudança de contrato
vira **diff revisável no PR** e esquecer de regenerar vira build vermelho.

### O gate morde — o par completo (Q12)

```
$ # A) `sse_starlette` em application, COM o módulo na lista
voicecoach.application is not allowed to import sse_starlette:
-   voicecoach.application.use_cases.process_turn -> sse_starlette (l.466)

$ # B) `starlette` em application, com o módulo REMOVIDO da lista
Contracts: 4 kept, 0 broken.
```

A metade B é a lacuna pré-existente: **a mesma linha de import passa verde** se o
módulo não estiver na lista. É a lição da Q8 aplicada a uma dependência que
estava lá desde o CARD-001.

### Gates

```
$ uv run ruff format --check src tests   →  106 files already formatted
$ uv run ruff check src tests            →  All checks passed!
$ uv run mypy                            →  Success: no issues found in 105 source files
$ uv run lint-imports                    →  Contracts: 4 kept, 0 broken.
$ uv run pytest --cov --cov-fail-under=80
   280 passed, 9 deselected in 8.78s
   Required test coverage of 80% reached. Total coverage: 92.63%
$ uv run coverage report --include="*/domain/*,*/application/*" --fail-under=90
   TOTAL  640  3  116  6   99%
```

(Eram 216 testes e 92,31% / 99% no fim do CARD-009.)

### Achados e divergências do que o card/prompt supunha

- **`Idempotency-Key` repetida não é falha** — muda a forma do `Result`
  (ADR-0039). O prompt afirmava que ela era "literalmente um dos três exemplos"
  do gatilho; é, e o exame de perto mostrou que o exemplo estava errado.
- **`Result` não atravessa gerador.** Descoberto ao escrever o stream: um gerador
  assíncrono não tem retorno que o consumidor leia, então "o turn não existe"
  continua sendo exceção mesmo sendo o mesmo tipo de desfecho que
  `SessionNotFound`. Inconsistência real, registrada nas consequências negativas
  do ADR-0039.
- **A porta `subscribe` teve de virar context manager.** Como gerador puro, o
  `SUBSCRIBE` só aconteceria na primeira iteração — e o caso de uso lê o banco
  antes disso. Todo evento publicado nessa janela cairia no chão, de forma
  intermitente e dependente do tempo do banco. Há teste para isso
  (`test_a_assinatura_acontece_antes_da_leitura_do_banco`) e outro contra Redis
  real.
- **Um teste passou pelo motivo errado, e custou 60 s para aparecer.** O
  fechamento no disconnect, escrito com `httpx`, ficava verde — em 60 s, porque
  quem fechava era o **prazo**, não a desconexão: o `ASGITransport` do httpx
  **não emite `http.disconnect`**. Reescrito falando ASGI direto: 0,006 s e
  assinatura devolvida. Um teste verde provando o contrário do que diz é pior que
  teste nenhum.
- **Erro 4xx não pode ser levantado dentro do gerador de um stream.** O Starlette
  recusa (*"Caught handled exception, but response already started"*): quando o
  primeiro byte sai, o código HTTP já foi enviado. A validação do `Last-Event-ID`
  passou para a rota. Está no ADR-0040, item 7.
- **Proxy que buferiza:** o `docker-compose.yml` **não tem proxy** (verificado);
  o uvicorn é falado direto e nada buferiza. Os cabeçalhos `Cache-Control:
  no-cache` e `X-Accel-Buffering: no` vão mesmo assim, com teste, porque no dia
  em que um proxy entrar ninguém vai lembrar disto.
- **Dois `conftest.py` colidem no `mypy`.** Um em `tests/` e outro em
  `tests/api/` viram o mesmo módulo. `explicit_package_bases` foi tentado e
  quebrou 288 outras checagens; a saída foi mover os dublês para
  `tests/fakes_api.py` e deixar as fixtures no único conftest.

### Dívidas registradas

| O que | Gatilho / card |
|---|---|
| `feedback` não é retomável | **CARD-013** (persistir correções) |
| Turn `queued` órfão quando o crash cai entre commit e enfileiramento | **CARD-025** (varredura), ou o retry do cliente |
| Sem autenticação: rotas `/v1` abertas, `DEV_STUDENT_ID` implícito | fase de auth (ADR-0007). O comportamento do token expirando **com stream aberto** já é dívida do ADR-0026 |
| Client HTTP fino em `packages/api-client` (só os tipos existem) | **CARD-012** |
| `ConflictingWriteError` é grosso: qualquer violação de unicidade em `turns` seria lida como colisão de idempotência | 2ª restrição de unicidade em `turns` (ADR-0042) |
| A ordem dos eventos que a retomada assume é a do `process_turn.py` de hoje | qualquer mudança na ordem de publicação (ADR-0041) |
| ADRs 0024–0029 seguem não destilados na skill | dívida herdada do CARD-004 |

### Regra do explicador

**Pergunta feita no ponto da decisão** (antes de escrever o código), sobre
consequência observável:

> *"O corpo de um gerador assíncrono não executa nada até o primeiro `__anext__`
> — chamar `events.subscribe(turn_id)` devolve o objeto e o `SUBSCRIBE` ainda não
> aconteceu. O caso de uso faz: `fluxo = subscribe(id)` → lê o Turn do banco →
> emite o histórico → `async for`. **O worker publica o `chunk:0` exatamente
> entre a leitura do banco e a primeira iteração. O que o aluno vê na tela, e o
> que acontece com esse trecho?"***

**Desfecho: em aberto.** Sem resposta e sem dispensa. Entra em
`docs/perguntas-em-aberto.md` como **Q13**.

**Q2, Q7 e Q12** foram reapresentadas na abertura: **nenhuma respondida, nenhuma
dispensada.** Seguem na fila. A **proposta de postmortem sobre a regra** também
segue sem resposta — sexta sessão seguida com o item vermelho, e o mecanismo
continua produzindo evidência sem produzir verificação.

> Ironia útil, pela sexta vez: **Q7 se demonstrou sozinha duas vezes nesta
> sessão**, com o `pytest` verde nas duas. O `mypy` reprovou `FakeTurnRepository`
> no instante em que `TurnRepository` ganhou `get_by_idempotency_key`, e
> `FakeTurnEvents` no instante em que `TurnEvents` ganhou `subscribe`. **Q12** se
> demonstrou no par completo acima. A demonstração existe; a resposta do
> desenvolvedor, não — e é ela que fecha o item (LEARNING-0004).

### Item de ADR da DoD — conferido contra critério escrito (LEARNING-0003)

Consultada a lista "Quando um ADR é OBRIGATÓRIO" de `docs/adr/README.md`:

| ADR | Critério(s) citado(s) |
|---|---|
| [0039](../adr/0039-result-minimo-para-desfecho-esperado-de-caso-de-uso.md) — `Result` | **2** (assinatura de todo caso de uso é fronteira), **5** (reverter obriga a tocar todo handler), **6** (fecha o "TBD" do ADR-0017, que a skill repete) |
| [0040](../adr/0040-formato-de-erro-da-api-problem-details.md) — Problem Details | **2** (o corpo do erro é contrato de API sob a política aditiva do ADR-0008) |
| [0041](../adr/0041-id-estruturado-do-evento-sse-e-retomada-derivada-do-banco.md) — `id` do SSE | **2** (o `id:` volta no `Last-Event-ID` e o servidor tem de honrar o formato para sempre) |
| [0042](../adr/0042-idempotencia-do-post-por-coluna-no-postgres.md) — idempotência | **2** (coluna nova + cabeçalho obrigatório), **4** (chave é dado do cliente, com retenção), **5** (migration com índice único) |

**Critério 1 (dependência externa) — conferido e NÃO gera ADR novo**, com o
motivo por escrito: `sse-starlette` **já havia sido escolhido** no ADR-0026
("Biblioteca: `sse-starlette` no backend", com a alternativa e o trade-off
registrados lá); este card apenas o instalou. `python-multipart` não é escolha —
é o único backend de multipart do FastAPI, e o `UploadFile` levanta na definição
da rota sem ele. As duas entraram nas listas `forbidden` no mesmo commit
(ADR-0012), junto do `starlette` que faltava.

**Critério 3 (custo recorrente) — não se aplica:** nenhum teste deste card gasta
um centavo; o teste pago do pipeline (`test_pipeline_integracao.py`, marcado
`slow`) não ganhou irmão.
