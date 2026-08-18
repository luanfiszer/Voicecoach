# CARD-012 — Upload com retry, polling com backoff e playback da resposta

- **ID:** CARD-012 · **Épico:** Fase 1 — Fatia vertical (fecha a fase)
- **Plataforma:** mobile · **Esforço:** M · **Status:** backlog
- **Dependências:** CARD-010, CARD-011

## Contexto

O fechamento da fatia vertical: o áudio gravado no CARD-011 percorre o
backend do CARD-010 e a resposta volta ao aparelho. Usa os tipos gerados em
`packages/api-client` (ADR-0008).

## Problema

Rede móvel falha; o app precisa de upload com retry + Idempotency-Key
(gerada no cliente, por tentativa de envio) e de acompanhar o job sem
travar a UI.

## Proposta técnica

- Client de API em `packages/api-client` (fetch tipado) consumido pelo app.
- Upload multipart com `Idempotency-Key` (uuid gerado ao concluir a
  gravação — retry reusa a mesma chave); retry com backoff limitado.
- Polling de `GET /v1/turns/{id}` **curto no início** (0,5–1s; backend é
  local — backoff só após ~10s) e timeout honesto; **UI progressiva**:
  transcrição + correções renderizam na etapa `speaking`, o áudio chega em
  seguida. Estados: enviando → transcrevendo → professor pensando →
  resposta em texto → áudio pronto.
- **Medição ponta a ponta** (gravei → texto visível → áudio tocável) logada
  no app em dev — valida o orçamento de latência da Fase 1 e aponta o
  gargalo real antes de qualquer otimização.
- Playback do áudio da URL assinada (expo-audio); tratar URL expirada
  (repedir o GET — ADR-0006).
- Exibir também o texto da resposta (transcript + spoken_reply) — as
  correções estruturadas ganham UI no CARD-016.

## Escopo

- **In:** o acima. **Out:** UI de correções (CARD-016); sessões explícitas
  com resumo (Fase 6); offline real (gatilho futuro).

## Critérios de aceite

- **Dado** um turn enviado, **quando** o processamento termina, **então**
  ouço a resposta no aparelho sem reiniciar o app (fluxo completo real:
  este é o critério de saída da Fase 1).
- **Dado** falha de rede no upload, **quando** o retry reenvia com a mesma
  chave, **então** o backend não cria turn duplicado.
- **Dado** polling excedendo o timeout, **então** a UI mostra erro honesto
  com ação de tentar de novo.

## Riscos

Latência total percebida (STT local + Haiku + TTS local) — medir de ponta a
ponta; se > 30s, registrar e investigar o gargalo antes de otimizar às cegas.

## Objetivo de aprendizado

Consumo de tipos gerados na prática (mudança de contrato quebra o build do
app) e o padrão de máquina de estados async na UI de RN — onde entram
AbortController, backoff e o caminho triste como cidadão de primeira classe.
