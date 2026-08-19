# CARD-010 — Endpoints de Turn: upload, idempotência e entrega progressiva por SSE

- **ID:** CARD-010 · **Épico:** Fase 1 — Fatia vertical em cascata
- **Plataforma:** backend · **Esforço:** M · **Status:** backlog
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
