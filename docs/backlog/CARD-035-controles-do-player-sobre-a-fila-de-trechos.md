# CARD-035 — Controles do player sobre a fila de trechos: velocidade, repetir e a barra que atravessa 3–6 áudios

- **ID:** CARD-035
- **Épico:** Fase 3 — Domínio pedagógico (artboard 06)
- **Plataforma:** mobile · **Esforço:** M · **Status:** backlog
- **Dependências:** CARD-028 (os estados fechados), CARD-012 (concluído); ADR-0047

## Contexto

O artboard 06 desenha quatro controles sobre a resposta do professor:
play/pause, **`0.75×`**, **`repetir`**, **scrub** (a barra com `0:05 / 0:12`) —
e `traduzir`, que é do CARD-016 (UI) e do CARD-036 (endpoint).

Em 2026-08-27 ficou decidido que **os quatro ficam**, scrub incluído. Este card
existe porque nenhum deles é trivial sobre o que o produto de fato entrega.

## Problema

**O design desenhou um player; o produto entrega uma fila.**

O ADR-0047 fixou "um player por trecho", e a resposta chega em **3–6 trechos**
com gap < 150 ms. Cada controle bate numa consequência diferente disso:

| Controle | O que quebra |
|---|---|
| **`0.75×`** | a taxa tem de ser aplicada a **todos** os trechos, inclusive aos que ainda **não chegaram** — mudar a velocidade no trecho 2 e o 5 voltar a 1× é o bug óbvio |
| **`repetir`** | "de novo" é o trecho 0, e ele pode já ter sido descartado da memória. Repetir depois do fim é diferente de repetir no meio |
| **scrub** | precisa de **duração total**, que só existe quando o último trecho chega — e de mapear uma posição global para *(trecho k, offset dentro dele)*. É o único dos quatro que exige estrutura nova |
| **play/pause** | o mais simples, e ainda assim: pausar entre trechos é um estado que não é "tocando" nem "parado" |

O artboard mostra `0:05 / 0:12` — um total conhecido desde o início. Durante a
cascata, **esse número não existe**.

## Requisitos funcionais

- **RF1** — A velocidade escolhida vale para a resposta **inteira**, incluindo
  trechos que chegarem depois da escolha, e persiste entre turns da mesma sessão.
- **RF2** — `repetir` toca a resposta do trecho 0, funcione ela em qualquer
  momento: durante a reprodução, depois do fim, e num turn já concluído do
  histórico da conversa.
- **RF3** — Enquanto a resposta ainda está chegando, a barra **não mente sobre o
  total**: ou não mostra total, ou o mostra como o que é (parcial e crescendo).
  Nunca um `0:12` fixo que muda de valor.
- **RF4** — Depois que todos os trechos chegaram, a barra mostra posição e
  duração totais e **o scrub funciona ponta a ponta**, atravessando a fronteira
  entre trechos sem silêncio audível.
- **RF5** — Arrastar para uma posição num trecho ainda não baixado é caso
  esperado, não erro: o comportamento é definido (esperar, ou limitar o alcance
  do arrasto ao que já chegou) e escrito.
- **RF6** — Os controles respeitam o alvo de toque de **48px** do style guide, e
  `0.75×` é um estado visível — o aluno precisa saber que está em câmera lenta.

## Requisitos não funcionais

- **RNF1 — Nada disto pode atrasar o primeiro áudio.** O orçamento é o p50 de
  2,34 s (ADR-0047) e ele é a regra de desempate do projeto inteiro. Se
  computar duração total exigir esperar trechos, **não se espera**: mostra-se
  parcial. Medir antes e depois, com a rota de medição que já existe.
- **RNF2 — Um dono do estado de reprodução.** Velocidade, posição e "qual trecho
  está tocando" são um estado só; espalhá-los entre `useFilaDePlayback` e o
  componente garante divergência. O hook que já existe é o lugar.
- **RNF3 — Sem vazar player.** Cada trecho tem seu player (ADR-0047); scrub e
  repetição criam e descartam mais. Um player não liberado é áudio tocando por
  cima de áudio — o bug mais audível possível.
- **RNF4 — Preferência é do aparelho, não do servidor.** A velocidade escolhida
  não vai para o backend: é preferência de UI, e a reconciliação de 2026-08-18 já
  recomendou não persistir isso no servidor.
- **RNF5 — Funciona no Simulador e o aparelho fica declarado.** O ADR-0048
  bloqueou o aparelho físico; o que não puder ser provado nele entra como dívida
  declarada, não como "funciona".

## Escopo

- **In:** os quatro controles; o estado unificado de reprodução; o mapeamento
  posição global ↔ trecho; o comportamento do RF5 decidido e escrito; medição de
  latência antes/depois.
- **Out:** `traduzir` (CARD-016 e CARD-036); controles sobre a fala **do aluno**
  (o `PlayerLocal` já existe e não é isto); download ou compartilhamento do
  áudio; equalização, waveform ou qualquer visualização além da barra.

## Critérios de aceite

- **Dado** `0.75×` escolhido no trecho 2 de 5, **então** os trechos 3, 4 e 5
  tocam em `0.75×` — inclusive os que ainda não tinham chegado.
- **Dado** uma resposta terminada, **quando** toco `repetir`, **então** ela
  recomeça do trecho 0 sem recarregar da rede o que já está local.
- **Dado** uma resposta ainda chegando, **então** a barra não exibe uma duração
  total fixa.
- **Dado** uma resposta completa de 5 trechos, **quando** arrasto de ponta a
  ponta, **então** o áudio segue a posição e não há silêncio audível na
  passagem entre trechos.
- **Dado** o p50 medido antes deste card, **então** o p50 depois **não** piora.
- **Dado** navegação para outra tela durante a reprodução, **então** nenhum
  player continua tocando.

## Riscos

- **Scrub é o card inteiro disfarçado de barra.** Se estourar, ele é o corte
  natural: `0.75×`, `repetir` e play/pause entregam valor sozinhos, e a barra
  vira card próprio. O contrário não é verdade.
- **Duração total tem duas definições** — soma das durações declaradas dos
  trechos (`ChunkPayload.duration_seconds`, que o servidor já manda) ou soma do
  que os players reportam. Elas divergem por arredondamento, e escolher uma é
  requisito, não detalhe.
- **`expo-audio` e `expo-av` estão em transição no SDK 54+.** Trocar de API no
  meio deste card é o tipo de coisa que consome a sessão inteira; confira o que
  o CARD-012 já usa antes de planejar.

## Objetivo de aprendizado

Controle de posição sobre uma sequência de áudios em RN — e por que "posição
global" é uma abstração que **você** constrói, não algo que o player oferece. O
paralelo mental em .NET é a diferença entre uma `Stream` concatenada e uma lista
de `Stream`s: só a primeira sabe onde está o byte 40.000.
