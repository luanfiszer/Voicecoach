# CARD-012 — Upload com retry, consumo do stream e playback encadeado (fecha a fatia)

- **ID:** CARD-012 · **Épico:** Fase 1 — Fatia vertical em cascata (fecha a fase)
- **Plataforma:** mobile · **Esforço:** M · **Status:** backlog
- **Dependências:** CARD-010, CARD-011; ADR-0026

## Contexto

O fechamento da fatia vertical, e o único lugar onde o alvo de 1,8 s pode ser
**verificado como o aluno o sente** — do dedo saindo do botão de gravar até a
primeira palavra sair do alto-falante.

## Por que agora

Todos os números do projeto são de componentes isolados. O **custo de composição**
— upload, pickup da fila, transporte, decodificação e início do playback — nunca
foi medido, e a [medição §1](../medicao-latencia.md) diz isso com todas as
letras. Este card é o primeiro número honesto do produto.

## Problema

Dois problemas novos, ambos do cliente:

1. **Consumir SSE em React Native.** O `EventSource` nativo **não aceita
   cabeçalho `Authorization`** — decidir entre `react-native-sse` (polyfill com
   headers) e o `fetch` com streaming do Expo, **sem sair do Expo Go** (a
   restrição do ADR-0002; sair para dev build é custo de V2).
2. **Playback encadeado sem buraco audível.** Tocar 4 arquivos em sequência com
   um gap perceptível entre frases desfaz o ganho: o aluno ouve um professor
   gaguejando. O trecho N+1 precisa estar **baixado e pronto** antes de o N
   terminar.

## Proposta técnica

- Client em `packages/api-client` (tipos gerados do OpenAPI — ADR-0008).
- Upload multipart com `Idempotency-Key` gerada ao concluir a gravação (o retry
  reusa a mesma chave); retry com backoff limitado.
- **Stream como caminho principal, polling como recuo** (ADR-0026): se o stream
  não abrir ou cair sem reconectar, o app cai para `GET /v1/turns/{id}` com
  backoff. Os dois caminhos são exercitados — o recuo que ninguém testa apodrece.
- **Fila de playback**: cada evento `chunk` entra numa fila; o player começa no
  primeiro e faz **prefetch do seguinte** enquanto toca. Métrica: gap entre
  trechos.
- Reconexão com `Last-Event-ID` ao voltar do background.
- URL de trecho expirada ⇒ repedir o GET (ADR-0024).
- **Medição ponta a ponta logada em dev**, com os marcos separados:
  `parei de falar → upload completo → primeiro chunk recebido → primeiro áudio
  audível`. **É este card que diz se 1,8 s foi entregue.**
- UI progressiva: transcrição e correções aparecem quando chegam; o áudio começa
  antes do texto do feedback — a ordem mudou por causa do ADR-0022, e a tela
  precisa refletir isso, não a ordem antiga.

## Escopo

- **In:** client tipado, upload com retry, consumo de SSE com recuo, playback
  encadeado, medição, tratamento de URL expirada.
- **Out:** UI de correções estruturadas (CARD-016); barge-in e realtime (V2);
  offline real.

## Critérios de aceite

- **Dado** uma frase gravada no aparelho físico, **então** ouço a primeira
  palavra da resposta em **≤ 2,4 s p50** medidos no app (o alvo é ~1,8 s; a folga
  é o custo de composição, que este card mede pela primeira vez). **Este é o
  critério de saída da fase.**
- **Dado** 4 trechos, **então** o gap audível entre eles é **< 150 ms** e não há
  reordenação (índice respeitado, não ordem de chegada).
- **Dado** o app em background por 5 s e de volta, **então** a reconexão retoma
  do último evento — sem repetir áudio já tocado.
- **Dado** o stream indisponível, **então** o app cai para polling e o turn
  completa (teste com SSE desligado por flag).
- **Dado** falha de rede no upload, **quando** o retry reenvia com a mesma
  chave, **então** o backend não cria turn duplicado.
- **Dado** um turn que falha depois de 2 trechos, **então** a UI diz o que
  aconteceu **sem** apagar o que já foi ouvido.

## Riscos

- **O polyfill de SSE pode exigir dev build.** Se exigir, o recuo é o `fetch`
  com streaming (Alternativa C do ADR-0026) — e, em último caso, polling curto,
  aceitando o custo de latência **com o número medido escrito no card**, não por
  omissão.
- Decodificar áudio no RN tem latência própria (não medida) que pode dominar o
  gap entre trechos.

## Objetivo de aprendizado

Máquina de estados async na UI de RN com `AbortController`, backoff e o caminho
triste como cidadão de primeira classe; e o consumo de tipos gerados na prática
— mudança de contrato quebra o build do app.
