# ADR-0003 — Modelo de interação: V1 turn-based, desenhado para V2 realtime

- **Status:** aceito
- **Data:** 2026-08-17

## Contexto

Com cliente próprio (ADR-0002), a interação não precisa mais ser "grava,
envia, espera, recebe MP3 pronto" — restrição que era do WhatsApp. O
desenvolvedor confirmou (sessão P2) que realtime é **ambição real do produto**:
conversa fluida, STT incremental, TTS em stream, interrupção do professor no
meio da fala. A questão é quanto o V1 deve pagar antecipadamente pelo V2.

## Decisão

**V1 turn-based**: upload de áudio → job assíncrono (fila + worker) → cliente
consulta status por **polling com backoff** → recebe correções estruturadas +
URL assinada do áudio de resposta.

**Costuras pagas no V1 para o V2** (baratas agora, caras depois):
1. Portas `SpeechToText`/`TextToSpeech` definidas como interface desde o dia 1;
   o V2 **adiciona** métodos de streaming (extensão), não altera os existentes.
2. `Turn` modelado sem assumir atomicidade — estados que acomodam o futuro
   turn parcial/interrompido (o V2 muda o ciclo de vida, não a entidade).
3. Transporte isolado na borda da API — trocá-lo não toca application/domain.
4. Pipeline do worker como passos componíveis (STT → LLM → TTS como funções
   encadeadas, não um bloco monolítico) — o V2 rearranja os mesmos passos em
   modo streaming.

**Costura deliberadamente NÃO paga**: WebSocket no V1. Polling resolve com uma
fração da superfície (sem gestão de conexão, reconexão, heartbeat) e o
transporte é descartável por desenho (item 3).

## O que muda de V1 para V2 (mapa de impacto)

| Aspecto | V1 | V2 | Sobrevive? |
|---|---|---|---|
| Transporte | HTTP upload + polling | WebSocket/WebRTC bidirecional | ❌ trocado (descartável por desenho) |
| STT | batch (arquivo completo) | incremental (chunks + parciais) | Porta sobrevive; adapter ganha variante |
| TTS | arquivo completo no storage | stream de chunks para o cliente | Idem |
| LLM | resposta única estruturada | streaming com possível corte (interrupção) | Porta sobrevive; prompt/contrato evoluem |
| Orquestração | job discreto na fila | pipeline contínuo com VAD/interrupção | ❌ reescrita (era ~1 arquivo do worker) |
| Domínio, auth, persistência, quotas, eval, observabilidade | — | — | ✅ intactos |
| Cliente mobile (captura) | expo-audio, gravação discreta | módulo nativo (ex.: WebRTC) em dev build | Telas sobrevivem; camada de áudio trocada |

**Estimativa de descarte V1→V2: ~15–20%** do backend (endpoints de
upload/polling + variante batch dos adapters + orquestração do worker), se as
costuras 1–4 forem respeitadas.

## Alternativas consideradas

### Alternativa A — Realtime direto no V1
- O que é: streaming bidirecional desde o primeiro app.
- Por que foi rejeitada: empilha os problemas mais difíceis (VAD, interrupção,
  jitter, módulo nativo de áudio, infra de WS) sobre um desenvolvedor iniciante
  em Python **e** em mobile, antes de existir baseline de qualidade pedagógica
  (P5) ou usuário. Contraria o aprendizado incremental; risco alto de abandono.

### Alternativa B — V1 minimalista sem costuras (otimizado só para simplicidade)
- O que é: turn-based sem portas formais, STT/TTS chamados direto no worker,
  modelo de Turn atômico.
- Por que foi rejeitada: as costuras 1–4 custam quase zero agora (são decisões
  de forma, não de código extra) e a ambição realtime é declarada. Sem elas, o
  V2 vira a reescrita nº 2 do projeto. Rejeitada também por desperdiçar o
  aprendizado de portas/adaptadores que o desenvolvedor quer consolidar.

### Alternativa C — V1 já com WebSocket (meio-termo)
- O que é: turn-based, mas entregando resultado por WS em vez de polling.
- Por que foi rejeitada: paga a superfície operacional do WS (reconexão,
  estado de conexão, auth de socket) sem entregar nenhuma feature que polling
  não entregue no V1. A lição do WS não se perde: virá inteira no V2, com
  motivo real.

## Consequências

**Positivas**: V1 entregável e testável cedo; aprendizado em degraus; domínio
e portas estáveis através da transição; descarte V1→V2 conhecido e aceito.

**Negativas — o preço aceito**: latência percebida do V1 é de "walkie-talkie"
(segundos entre fala e resposta), abaixo do padrão de apps de conversação
modernos — aceito como degrau; UX do app precisa ser honesta sobre o
processamento (estados de progresso). Polling gasta requests (mitigado com
backoff). A estimativa de 15–20% de descarte pode crescer se as costuras forem
violadas em nome de atalhos.

**Gatilho de início do V2**: V1 estável + eval harness com baseline (P5) +
uso próprio regular por algumas semanas.
