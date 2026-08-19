# ADR-0026 — Entrega progressiva do turn por SSE, com o polling preservado como contrato de recuo

- **Status:** aceito
- **Data:** 2026-08-19
- **Relacionado:** ADR-0003 (transporte é a parte descartável), ADR-0008
  (contrato aditivo), ADR-0023 (trechos), ADR-0024 (URL junto do evento),
  visão §F (WebSocket cortado, com gatilho)
- **Critérios de obrigatoriedade:** **2 — define uma fronteira** (contrato de
  API e transporte) e **1 — introduz dependência externa** (`sse-starlette` no
  backend; polyfill de `EventSource` no cliente).

## Contexto

Com a cascata (ADR-0023), o servidor tem algo novo para dizer ao cliente **de 3
a 6 vezes por turn**, e o valor de dizer cedo é o produto inteiro: o alvo é o
aluno ouvir a primeira frase em ~1,8 s.

O CARD-010 original especificou **polling** (`GET /v1/turns/{id}` com backoff),
e a visão §F cortou WebSocket com gatilho escrito: *"primeira feature de push
real"*. A entrega de áudio em trechos **é** essa feature — o gatilho disparou.

O que o polling custa, com números:

- Intervalo de 500 ms ⇒ **250 ms de latência média de descoberta por trecho** —
  ~14% de um orçamento de 1,8 s, gasto em espera pura.
- Para descobrir em ~100 ms seria preciso pollar a 200 ms: **5 requisições por
  segundo, por turn ativo**, cada uma com auth, query e serialização.
- E o pior caso não é a média: o trecho pode ficar pronto logo depois de uma
  resposta, pagando o intervalo inteiro.

A [análise §4](../analise-caminho-para-1-2s.md) registra a reversão: o SSE havia
sido descartado como "a menor alavanca da lista" sob o orçamento de 12–15 s;
sob ~1,8 s ele volta à mesa.

## Decisão

**A entrega progressiva de um turn acontece por Server-Sent Events, num endpoint
novo. O `GET /v1/turns/{id}` continua existindo, completo e correto, como
contrato de recuo.**

1. **`GET /v1/turns/{id}/events`** — `text/event-stream`, autenticado como
   qualquer outro endpoint. Eventos nomeados, todos com `id` para permitir
   retomada:

   | Evento | Payload | Quando |
   |---|---|---|
   | `transcribed` | `{transcript}` | STT terminou |
   | `chunk` | `{index, url, duration_seconds, text}` | um trecho de áudio ficou pronto |
   | `feedback` | `{has_mistakes, original, corrected, tip}` | o JSON do professor fechou |
   | `completed` | `{reply_audio_url, ...}` | turn completo |
   | `failed` | `{reason, delivered_partially}` | falha, inclusive depois de entrega parcial |

2. **A URL assinada viaja no evento** (ADR-0024): o cliente não faz roundtrip
   para descobrir onde está o áudio.
3. **Retomada por `Last-Event-ID`.** Reconectar no meio do turn reenvia os
   eventos que faltaram, a partir dos trechos persistidos (ADR-0023) — é o que
   torna a entrega retomável em vez de efêmera, e o que faz "o app foi para
   background" deixar de ser perda de dados.
4. **`GET /v1/turns/{id}` permanece verdadeiro e completo**, agora com
   `chunks[]` (campo **aditivo** — ADR-0008). Cliente antigo, cliente sem SSE e
   caminho triste de rede continuam funcionando com polling. **O SSE é uma
   otimização de latência sobre um contrato que se sustenta sem ele.**
5. **O stream tem prazo:** timeout de servidor por turn (default 60 s, em
   `Settings`) e fechamento no `completed`/`failed`. Stream aberto para sempre é
   conexão vazando.
6. **Não é WebSocket, e isto não é o V2.** O canal é unidirecional
   (servidor→cliente), sobre HTTP comum, sem protocolo novo, sem VAD, sem
   barge-in, sem módulo nativo. O gatilho do ADR-0003 continua intocado.

**Biblioteca:** `sse-starlette` no backend — é o wrapper de `EventSourceResponse`
que trata heartbeat, desconexão do cliente e o formato do protocolo; a
alternativa é montar `StreamingResponse` com o formato de `text/event-stream` na
mão, o que é ~40 linhas de protocolo textual fácil de errar em detalhe (linha em
branco separando eventos, `retry:`, comentário de keep-alive). No cliente, o
`EventSource` nativo **não permite cabeçalho `Authorization`**, então entra
`react-native-sse` (polyfill que aceita headers) ou o `fetch` com streaming do
Expo — decisão do CARD-012, à luz do que o Expo Go suporta sem dev build.

## Alternativas consideradas

### Alternativa A — Polling curto (o desenho original do CARD-010)

- **O que é:** `GET /v1/turns/{id}` a cada 300–500 ms enquanto o turn roda.
- **Por que foi rejeitada como caminho principal:** os 250 ms médios de
  descoberta saem direto do orçamento de 1,8 s, e apertar o intervalo troca
  latência por carga (5 req/s por turn ativo). Sob a regra de desempate escrita
  ("se algo ceder, cede escopo, nunca latência"), é o que cede. **Preservada
  como recuo** — item 4 — porque é o único caminho que funciona quando o stream
  não é possível.

### Alternativa B — WebSocket

- **O que é:** canal bidirecional persistente.
- **Por que foi rejeitada:** entrega o mesmo que o SSE para este caso (o cliente
  não tem nada a dizer durante o turn) e cobra a superfície inteira que a visão
  §F cortou: protocolo próprio, autenticação fora do fluxo HTTP normal,
  reconexão manual, proxies e infraestrutura que precisa saber de upgrade. O
  bidirecional só se paga com **barge-in**, que é V2 declarado.

### Alternativa C — HTTP chunked com NDJSON (streaming de resposta comum)

- **O que é:** uma resposta longa, uma linha JSON por evento.
- **Por que foi rejeitada:** é SSE reinventado sem as partes que já vêm de
  graça: retomada por `Last-Event-ID`, reconexão automática do cliente,
  keep-alive padronizado e tipo de evento. Tecnicamente viável e um pouco mais
  fácil de consumir com `fetch` streaming no RN — fica registrada como saída
  caso o polyfill de `EventSource` se mostre inviável no Expo Go.

### Alternativa D — Push por notificação (Expo Notifications)

- **O que é:** o servidor avisa por push que há trecho novo.
- **Por que foi rejeitada:** latência de push não é controlável nem medível em
  fração de segundo, e depende de serviço de terceiro no caminho crítico. Push
  serve para reengajar quem não está no app; aqui o aluno está com o telefone na
  mão, esperando.

## Consequências

**Positivas**

- Elimina a latência de descoberta: o trecho chega quando existe, já assinado.
- A carga cai em vez de subir: uma conexão por turn em vez de N requisições.
- `Last-Event-ID` dá retomada de graça — o caminho triste de rede móvel fica
  mais barato do que era com polling e retry.

**Negativas — o preço aceito**

- **Uma superfície de transporte a mais para manter**, exatamente a que a visão
  §F tinha cortado. O gatilho disparou, mas o custo é real: dois caminhos de
  entrega (SSE e polling) precisam **ambos** ser testados, ou o recuo apodrece.
- **Conexões longas mudam o desenho operacional**: cada turn ativo segura um
  worker do uvicorn; proxies e balanceadores precisam não bufferizar
  `text/event-stream`, e isso costuma ser descoberto em produção.
- **O cliente RN precisa de polyfill** — dependência a mais no app, e risco de
  esbarrar no limite do Expo Go, que é justamente o que o ADR-0002 quis evitar.
- **Autenticação em stream é mais chata**: o token pode expirar com a conexão
  aberta. Nesta fase o token é fixo de dev; quando a auth real entrar (ADR-0007),
  o comportamento na expiração precisa ser decidido — dívida registrada.
- **Duplicação de lógica de serialização**: o payload do evento e o do
  `GET /v1/turns/{id}` descrevem a mesma coisa de duas formas. Devem sair do
  mesmo schema pydantic, ou divergem.
