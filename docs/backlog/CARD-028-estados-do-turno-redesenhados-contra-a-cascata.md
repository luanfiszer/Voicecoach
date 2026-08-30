# CARD-028 — Os estados do turno redesenhados contra a cascata: o design volta a descrever o produto

- **ID:** CARD-028
- **Épico:** Fase 2 — Domínio pedagógico (abre, porque o CARD-016 renderiza em cima disto)
- **Plataforma:** mobile/design · **Esforço:** P · **Status:** backlog
- **Dependências:** CARD-012 (concluído); ADR-0022, ADR-0023, ADR-0026, ADR-0028, ADR-0047

## Contexto

O `Design.pdf` é de **2026-08-17**. A cascata é de **2026-08-19**. Os quatro
artboards de estado (03–06) foram desenhados sob um orçamento de latência que
não existe mais, e o `docs/design/README.md` já registra a divergência — mas
registra como aviso, não como decisão. Aviso não impede ninguém de implementar
a tela errada.

O CARD-016 vai renderizar correções **sobre** esses estados. Ele precisa saber
quais são.

## Problema

**O app já diverge do design, e ninguém decidiu que divergiu.**

A máquina que existe hoje (`TelaConversa.tsx:125`, `useTurno.ts`) é
`ocioso → enviando → transcrevendo → ouvindo → concluido | falhou`. O design
descreve outra coisa:

| Artboard | O que promete | O que o produto faz |
|---|---|---|
| **03** transcrevendo | *"Passo 1 de 3 · você pode guardar o telefone, avisamos com som"*, com barra proporcional | o primeiro áudio sai em **1,6 s**. Mandar guardar o telefone é errado. E "3 passos" enumera uma granularidade que o ADR-0028 decidiu **derivar**, não expor |
| **04** professor pensando | um estado próprio | o app **pula** de `transcrevendo` para `ouvindo`. A etapa dura ~0,8 s: desenhar tela para ela é piscar |
| **05** texto primeiro | *"Você já pode ler; o áudio toca sozinho quando chegar"* | **invertido** — o áudio vem primeiro (ADR-0022), o feedback fecha **depois** do último trecho |
| **06** player | **um** player, **uma** duração (`0:05 / 0:12`), com scrub | **3–6 trechos** em fila, gap < 150 ms (ADR-0047). Scrub sobre uma fila é outro controle |

Consequência prática: a tela que o produto real precisa — **"áudio tocando,
feedback a caminho"** — não existe desenhada em lugar nenhum.

## Proposta técnica

Card de **decisão + reconciliação**, não de feature nova.

- **Fechar a lista de estados que o app mostra**, derivada do que o servidor de
  fato entrega (o `stage` do ADR-0028 e os eventos SSE do ADR-0026), e não do
  que o design imaginou. O ponto de partida é a máquina que já roda —
  ela venceu na prática e o card decide se ela venceu com razão.
- **Matar o que morreu, por escrito:** o "Passo 1 de 3", a barra proporcional, o
  "guarde o telefone", o estado próprio de "pensando". Cada um com uma linha de
  motivo, no `docs/design/README.md`, para que ninguém os reimplemente por
  encontrar o PNG.
- **Descrever o estado que falta:** áudio tocando **enquanto** o feedback ainda
  vem. É o estado central do produto e o único sem desenho. Não precisa de
  artboard novo do Claude Design — precisa de descrição escrita e do componente,
  usando o style guide do artboard 17 que já está em `theme/tokens.ts`.
- **O player já foi decidido (2026-08-27): as quatro affordances ficam.**
  Transporte, `0.75×`, `repetir` e **scrub** — inclusive o scrub, que é o único
  que não sai de graça sobre uma fila de 3–6 trechos. Elas não moram aqui:

  | Affordance | Onde |
  |---|---|
  | play/pause, `0.75×`, `repetir`, scrub | **[CARD-035](CARD-035-controles-do-player-sobre-a-fila-de-trechos.md)** |
  | `traduzir` (a UI) | CARD-016 |
  | `traduzir` (o endpoint) | **[CARD-036](CARD-036-traducao-sob-demanda.md)** |

  O que **fica** neste card é a consequência de forma: um player sobre uma fila
  não pode mostrar duração total antes do último trecho chegar, e é isso que a
  tela precisa saber dizer.

## Escopo

- **In:** a lista de estados fechada e escrita; o `docs/design/README.md`
  atualizado de "aviso" para "decisão", artboard a artboard; o estado "áudio
  tocando, feedback a caminho" implementado na `TelaConversa`.
- **Out:** o card de correção (CARD-016) e o resumo de sessão (CARD-016);
  telas de exceção (CARD-027); qualquer redesenho visual além de aplicar os
  tokens que já existem; gerar artboards novos.

## Critérios de aceite

- **Dado** o `docs/design/README.md`, **então** cada artboard de 03 a 06 tem um
  veredito explícito — vale / vale em parte (com o quê) / morreu (por quê) — e
  nenhum fica só com "reconciliar contra os ADRs".
- **Dado** um turn em que o primeiro trecho de áudio chegou e o feedback não,
  **então** a tela mostra o estado próprio disso, e **não** um spinner genérico
  nem "transcrevendo".
- **Dado** um turn completo, **então** nenhuma tela promete uma duração total
  antes de todos os trechos terem chegado — porque ela não é conhecida.
- **Dado** o app, **então** nenhum texto de UI enumera "passo N de 3".

## Riscos

- **Card de decisão vira card de redesenho.** A tentação é abrir o Claude Design
  e regenerar tudo. O gatilho para isso seria uma tela nova de verdade; aqui há
  uma, e ela cabe no style guide existente.
- **O player já abriu dois cards** (035 e 036). O risco agora é o inverso: este
  card implementar "só um pedacinho" de controle de áudio de passagem. Se
  encostar em velocidade, repetição ou posição, parou — é o CARD-035.

## Objetivo de aprendizado

Como o `expo-av`/`expo-audio` expõe posição e duração de uma **fila** de
áudios contra um arquivo só — e por que "duração total" é um valor que só existe
no fim, o que em C# seria a diferença entre um `IEnumerable` que você já
materializou e um `IAsyncEnumerable` que ainda está chegando.
