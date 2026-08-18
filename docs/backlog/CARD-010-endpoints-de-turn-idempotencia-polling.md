# CARD-010 — Endpoints de Turn: upload multipart, Idempotency-Key, 202 + polling

- **ID:** CARD-010 · **Épico:** Fase 1 — Fatia vertical
- **Plataforma:** backend · **Esforço:** M · **Status:** backlog
- **Dependências:** CARD-009

## Contexto

Visão §D (fluxo do Turn) e ADR-0008 (contrato /v1, OpenAPI como fonte dos
tipos). A idempotência renasce aqui como requisito da nova API (F4
revisado). Auth: token fixo de dev nesta fase (Fase 3 substitui — decisão do
roadmap).

## Problema

O pipeline existe mas não tem borda HTTP; o app (CARD-012) precisa do
contrato completo: enviar áudio, acompanhar status, receber resultado.

## Proposta técnica

- `POST /v1/sessions/{id}/turns`: multipart (áudio) + header
  `Idempotency-Key`; valida content-type e **duração** (metadata, não só MB
  — lição §7.4); salva input no storage; cria Turn; enfileira; `202
  {turn_id}`. Chave repetida ⇒ mesmo turn_id, sem reprocessar (Redis
  SETNX+TTL).
- `GET /v1/turns/{id}`: status + payload completo quando `completed`
  (transcript, feedback, `reply_audio_url` assinada) — schemas pydantic
  espelhando `TeacherFeedback`.
- `POST /v1/sessions` mínimo (abre sessão para o Student dev).
- Exception handlers Problem Details (RFC 9457) — visão §D.
- Geração `openapi-typescript` ligada de verdade no CI (placeholder do
  CARD-003 vira real).
- Testes de rota com httpx (fluxo feliz com worker fake/inline; idempotência;
  erros).

## Escopo

- **In:** o acima. **Out:** auth real (Fase 3); quotas (CARD-015); telas
  (CARD-011/012).

## Critérios de aceite

- **Dado** o mesmo `Idempotency-Key` duas vezes, **então** o segundo POST
  retorna o mesmo `turn_id` e só existe um Turn no banco.
- **Dado** upload sem áudio válido, **então** 422 em formato Problem Details.
- **Dado** um turn `completed`, **quando** GET, **então** a resposta valida
  contra o schema e a URL de áudio é assinada.
- **Dado** o CI, **então** `packages/api-client` contém tipos gerados do
  OpenAPI atual e o diff é visível no PR.

## Riscos

Idempotência entre "criei o Turn" e "enfileirei" tem janela — ordem das
operações e o SETNX precisam de atenção (bom material de pergunta do
explicador).

## Objetivo de aprendizado

Multipart + streaming de upload no FastAPI (UploadFile, SpooledTemporaryFile
— o que há de `IFormFile` aqui) e o desenho de idempotência com Redis:
por que SETNX+TTL, o que acontece no crash entre passos.
