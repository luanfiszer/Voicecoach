# CARD-017 — Retenção de áudio: lifecycle, expiração e delete por prefixo

- **ID:** CARD-017 · **Épico:** Fase 2 — Proteção de custo/privacidade (fecha a fase)
- **Plataforma:** backend/infra · **Esforço:** P · **Status:** backlog
- **Dependências:** CARD-008, CARD-010

## Contexto

ADR-0006 (retenção como regra explícita) e visão §E (LGPD não adia: TTLs e
direito de exclusão nascem no MVP). O F6 do diagnóstico termina de morrer
aqui — a metade "disco enche / dado retido para sempre".

## Problema

Áudios acumulam sem política: input não precisa viver mais que dias;
resposta não precisa viver para sempre; e delete de conta precisa apagar
tudo.

## Proposta técnica

- Lifecycle rules no bucket (via código de setup, não clique): input expira
  em `AUDIO_INPUT_TTL_DAYS` (default 7), resposta em
  `AUDIO_REPLY_TTL_DAYS` (default 90) — valores em Settings, citados na
  política de privacidade.
- `MediaStorage.delete_prefix(student_id)` na porta + implementação — usada
  pelo delete de conta (endpoint completo vem na Fase 5; a operação de
  storage nasce aqui testada).
- `GET /v1/turns/{id}` de turn com áudio expirado: resposta degrada honesta
  (transcript e correções permanecem; áudio marcado indisponível).
- Documentar a matriz de retenção em `docs/` (fonte para a política de
  privacidade).

## Escopo

- **In:** o acima. **Out:** endpoint de delete de conta e export (Fase 5);
  UI de "áudio expirado" (Fase 6 usa o campo do contrato).

## Critérios de aceite

- **Dado** o setup do bucket, **então** as lifecycle rules existem com os
  TTLs da config (verificado por teste de integração lendo a configuração
  do MinIO).
- **Dado** `delete_prefix` de um student com N objetos, **então** zero
  objetos restam sob o prefixo e os de outros students permanecem.
- **Dado** um turn cujo áudio expirou (simulado), **então** o GET responde
  200 com `reply_audio: unavailable` — não 500.

## Riscos

Diferenças de lifecycle entre MinIO e S3 real (nota do ADR-0006) — teste
cobre MinIO; revalidar no provedor se um dia migrar.

## Objetivo de aprendizado

Lifecycle de object storage como mecanismo de compliance (retenção que se
cumpre sozinha vs cron caseiro) e degradação honesta de contrato quando um
recurso referenciado deixa de existir.

## Ajuste da reconstrução (2026-08-19)

O [ADR-0024](../adr/0024-midia-por-trecho-chave-url-assinada-e-retencao-assimetrica.md)
substituiu o ADR-0006 e mudou o escopo deste card: a retenção agora é
**assimétrica** — trecho (1 dia), áudio inteiro (90 dias), input (7 dias). São
três regras de lifecycle, não duas.

Acrescenta-se um caso de degradação honesta: **trecho expirado com `full`
presente** ⇒ o cliente toca o áudio inteiro, sem erro. Só quando os dois somem é
que o áudio vira indisponível.
