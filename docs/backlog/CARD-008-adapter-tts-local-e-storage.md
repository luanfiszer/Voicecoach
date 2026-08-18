# CARD-008 — Porta TextToSpeech (Kokoro local) + porta MediaStorage (MinIO, URL assinada)

- **ID:** CARD-008 · **Épico:** Fase 1 — Fatia vertical
- **Plataforma:** backend/IA · **Esforço:** M · **Status:** backlog
- **Dependências:** CARD-002; padrão de porta do CARD-006

## Contexto

ADR-0011 (TTS local default) e ADR-0006 (S3/MinIO, URL assinada com TTL,
chaves por usuário). Juntos porque o output do TTS vai direto para o storage
— o F6 do diagnóstico morre neste card.

## Problema

O protótipo servia MP3 públicos eternos do filesystem; a fatia precisa de
áudio de resposta armazenado com acesso controlado e expirável.

## Proposta técnica

- Porta `TextToSpeech`: `synthesize(text) -> AudioData`; adapter Kokoro
  (CPU, via executor — mesmo padrão do CARD-006); esqueleto OpenAI TTS atrás
  de `TTS_PROVIDER`.
- Porta `MediaStorage`: `put(key, data)`, `presigned_get_url(key, ttl)`;
  adapter S3 (boto3 contra MinIO). Chaves:
  `{student_id}/{session_id}/{turn_id}/{kind}.{ext}`.
- TTLs de retenção do ADR-0006 configurados (lifecycle) — valores em
  Settings.
- Testes: storage contra MinIO real (roundtrip + URL assinada expira);
  TTS marcado slow (gera áudio não-vazio).

## Escopo

- **In:** o acima. **Out:** streaming de TTS (V2); delete por prefixo
  (CARD-017); upload do áudio de entrada (CARD-010, na borda).

## Critérios de aceite

- **Dado** um texto, **quando** o pipeline sintetiza e armazena, **então**
  a URL assinada retornada toca o áudio e **expira** após o TTL (teste com
  TTL curto).
- **Dado** acesso direto ao bucket sem assinatura, **então** o objeto não é
  legível (bucket privado).
- **Dado** `TTS_PROVIDER=openai` sem chave, **então** boot falha claro.

## Riscos

Qualidade/naturalidade do Kokoro para dicas de pronúncia — risco aceito no
ADR-0011 (dev), medido no eval antes de promover; peso do modelo local.

## Objetivo de aprendizado

Presigned URLs na prática (quem assina, o que a assinatura carrega, por que
o backend sai do caminho dos bytes) e boto3 síncrono em app async — decidir
conscientemente entre executor e aioboto3, documentando o trade-off.
