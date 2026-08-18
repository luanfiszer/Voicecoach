# CARD-006 — Porta SpeechToText + adapter faster-whisper local

- **ID:** CARD-006 · **Épico:** Fase 1 — Fatia vertical
- **Plataforma:** backend/IA · **Esforço:** P · **Status:** backlog
- **Dependências:** CARD-001 (estrutura); paralelo a CARD-005

## Contexto

ADR-0011: STT local por default (custo zero), API por config. ADR-0003:
porta desenhada para ganhar variante streaming no V2 por extensão.

## Problema

Primeira porta real do sistema — define o padrão que as demais seguem.

## Proposta técnica

- `application/ports/speech_to_text.py`: `Protocol` com
  `transcribe(audio: AudioInput) -> Transcript` (tipos próprios — não vazar
  tipos da lib pela porta).
- `adapters/stt/faster_whisper_adapter.py`: modelo `small` (config), língua
  forçada `en` (preserva decisão do protótipo), execução em
  `run_in_executor`/thread — **a lição do F3**: CPU-bound não bloqueia o
  event loop do worker.
- Esqueleto do adapter OpenAI (`stt/openai_adapter.py`) atrás de
  `STT_PROVIDER` — implementação plena só quando o modo qualidade for usado.
- Teste: fixture de áudio curto conhecido; asserção tolerante (contém
  palavras-chave, não igualdade exata).

## Escopo

- **In:** porta, adapter local funcional, seleção por config, teste.
- **Out:** streaming (V2); métricas de WER (eval, Fase 4).

## Critérios de aceite

- **Dado** um wav/m4a de teste dizendo "hello teacher", **quando**
  `transcribe` roda, **então** o texto contém "hello" (integração, marcada
  slow).
- **Dado** `STT_PROVIDER=openai` sem chave, **então** o boot falha com
  mensagem clara (config fail-fast).
- **Dado** a porta, **quando** application é testada, **então** usa um fake
  em memória sem tocar em faster-whisper.

## Riscos

Download do modelo no primeiro uso (tamanho/tempo) — cachear e documentar;
performance em máquinas fracas — registrar requisito no README.

## Objetivo de aprendizado

`Protocol` na prática (interface estrutural: o fake do teste não declara
implements — só tem o método certo) e o padrão `run_in_executor` para
CPU-bound em código async — o paralelo de `Task.Run` para não bloquear o
scheduler, com a diferença do GIL explicada.
