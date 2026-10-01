# CARD-065 — Web, fase 2: a conversa por áudio no navegador

- **ID:** CARD-065
- **Épico:** Web companion
- **Esforço:** G
- **Status:** backlog
- **Dependências:** [CARD-064](CARD-064-web-companion-fase-1.md) (sessão e casca do app web), ADR-0023, ADR-0026, ADR-0046, ADR-0047

## Contexto

Segunda fase pedida pelo desenvolvedor em 2026-10-01: a tela de conversa do
mobile, no navegador. É a parte que o ADR-0001 chamou de "possível, mas não o
foco" da web.

## Proposta técnica

- Gravação com `MediaRecorder` (Opus/WebM no Chrome/Firefox, MP4/AAC no
  Safari) — o backend aceita? **verificar** `audio_intake.extensao_para`
  antes de escolher o formato.
- Permissão de microfone pelo navegador (`getUserMedia`), com o overlay
  equivalente ao artboard 13.
- Entrega progressiva: o mesmo `acompanharTurn` (SSE por `fetch`) do mobile,
  com recuo para polling; fila de trechos com `HTMLAudioElement`, sem gap
  audível (critério do ADR-0047: < 150 ms).
- Correções, traduzir, descartar turn travado, overlays de cota/pausa.

## Critérios de aceite

- **Dado** o Chrome e o Safari, **quando** o aluno grava, **então** o turn
  completa e a resposta toca.
- **Dado** a resposta em trechos, **então** o intervalo entre trechos é
  medido e fica abaixo de 150 ms.
- **Dado** a permissão negada, **então** a tela explica como liberar, sem
  travar.

## Objetivo de aprendizado

A API de mídia do navegador (`MediaRecorder`, `getUserMedia`, autoplay
policy) contra o `expo-audio` — o mesmo produto em duas plataformas de áudio
com regras diferentes.
