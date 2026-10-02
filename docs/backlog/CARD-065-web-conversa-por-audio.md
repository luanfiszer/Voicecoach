# CARD-065 — Web, fase 2: a conversa por áudio no navegador

- **ID:** CARD-065
- **Épico:** Web companion
- **Esforço:** G
- **Status:** concluído (2026-10-02) — Chromium e Firefox verificados; Safari não (ver "Dívida")
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

## Execução (2026-10-02)

### Pergunta do explicador (ponto da decisão do formato de gravação)

*"O WebM do `MediaRecorder` sai sem duração no cabeçalho — o que o `POST` de
turn responde, e com que duração desconta a cota?"* → **dispensada pelo
desenvolvedor** ("continue"). **O que a execução demonstrou:** gravado no
Chromium com microfone simulado, `audio/webm;codecs=opus`, PyAV lê
`stream.duration: None`; o `POST` respondeu **202** e a cota descontou
**3,96 s**, porque o backend mede a duração pelas amostras decodificadas
(`audio_intake.medir`), não pelo cabeçalho. **Nenhuma mudança de backend foi
necessária para a web gravar.**

### O que entrou

- `features/conversa/`: `formatoDeGravacao` (WebM/Opus no Chrome/Firefox,
  MP4 no Safari), `useGravacao` (`getUserMedia` + `MediaRecorder`, permissão
  lida da plataforma, limite de 90 s por relógio a partir do `start`),
  `filaDePlayback` (um `HTMLAudioElement` por trecho criado na chegada,
  ordem por índice, dedup, vigia de 4 s, `pause()` antes de soltar —
  LEARNING-0006), `useTurno` (SSE com recuo para polling, `Idempotency-Key`
  por gravação, tradução, descartar, overlays de cota/pausa/rede/travado),
  `TelaConversa`, `BotaoGravar` (84 px, círculo/quadrado/pulso).
- **`rejected` tratado** (CARD-040): o cliente TypeScript ignorava o evento;
  agora ele está no `EventoDoTurn` (aditivo) e a web mostra o convite a
  repetir — *"Não entendi, pode repetir?"*, *"Não ouvi nada…"*, *"Isso não
  pareceu inglês…"*. O mobile segue sem tratar: virou o
  [CARD-066](CARD-066-mobile-trata-o-turn-recusado.md).
- Testes novos: `filaDePlayback` (6), `formatoDeGravacao` (4),
  `rotulosDaConversa` (4), `excecoes` (2), `eventos` do `api-client` (1).

### QA no navegador real

| Cenário | Resultado |
|---|---|
| Chromium, fala em inglês | transcrição, resposta em trechos, **primeiro som 1,96 s** depois de parar, **gap 1 ms** entre trechos (critério < 150 ms), tradução "Que maravilhoso! Parece que você…", sem erro no console |
| Chromium, fala em português (`pt-br-curto.wav`) | "Isso não pareceu inglês. Pode repetir em inglês?" |
| Chromium, silêncio | convite a repetir |
| **Firefox**, tom sintético | `POST` 202 com WebM/Opus; "Não ouvi nada. Pode repetir…" |
| Botão de gravar parado × gravando | mesma posição (y=733) nos dois motores — corrigido um pulo do botão para o topo achado nas capturas |

Dois achados do próprio QA: o botão pulava de lugar com a lista vazia
(corrigido); e uma verificação do roteiro dava **falso positivo** na
tradução (casava com o subtítulo acentuado) — reescrita para olhar dentro da
bolha do professor.

### ADR

Nenhum critério de `docs/adr/README.md` se aplica: sem dependência nova (só
APIs do navegador); o contrato do servidor não muda (o `rejected` já estava no
OpenAPI desde o CARD-040 — o cliente só passou a lê-lo); as escolhas de
playback repetem o ADR-0047 sobre outra plataforma; nada é difícil de
reverter.

### Dívida

- **Safari não verificado.** A gravação em MP4 e a política de autoplay do
  Safari (que pode exigir gesto por elemento de áudio) não foram exercitadas
  — o Playwright não simula microfone no WebKit. Verificar num Mac com Safari
  antes de anunciar a web como suportada nele.
- Retomar o stream depois de queda de rede usa só o polling (sem
  `Last-Event-ID` automático na web).
