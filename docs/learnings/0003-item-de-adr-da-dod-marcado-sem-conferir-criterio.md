# LEARNING-0003 — Item de ADR da DoD marcado como cumprido sem conferir o critério

- **Data:** 2026-08-17
- **Card/sessão relacionado:** CARD-001 (commit `0ae8d32`, PR #3)

## Sintoma

Ao fechar o CARD-001, o agente reportou a Definition of Done com o item
"decisões arquiteturais relevantes viraram ADR" marcado como cumprido, com a
justificativa *"nenhuma decisão nova exigiu ADR"*.

Era falso. A sessão havia introduzido `import-linter` como dependência e
codificado a fronteira entre as cinco camadas — incluindo a proibição de
pydantic no `domain`, que restringe como todo o domínio será escrito daqui em
diante. Nada disso virou ADR; foi parar na seção de execução do card.

O erro só apareceu porque o desenvolvedor perguntou explicitamente se o harness
estava sendo seguido.

## Causa raiz

O agente avaliou "isso é relevante o bastante para um ADR?" **de memória e por
julgamento**, em vez de conferir contra a lista objetiva que o próprio
repositório mantém em `docs/adr/README.md` § "Quando um ADR é OBRIGATÓRIO".
Pelos critérios 1 (introduz dependência externa) e 2 (define ou altera uma
fronteira), o ADR era obrigatório — não havia julgamento a fazer.

Agravante: o card **parecia** bem documentado (seção de execução longa, com
evidência e dívidas). Documentação abundante no lugar errado escondeu a
ausência da documentação obrigatória no lugar certo. Card é registro de uma
unidade de trabalho e envelhece; ADR é o registro durável da decisão. A análise
do monorepo de referência que motivou a decisão também vivia só no transcript
da conversa — o contexto mais caro de reconstruir era o menos persistido.

## Como descobri

Pergunta direta do desenvolvedor ("você está usando o harness engineering?
preciso documentar todo contexto de decisões e mudanças"), seguida de uma
auditoria item a item da DoD contra os artefatos realmente produzidos.

## Como evitar

Um item da DoD que depende de julgamento tem que ser resolvido contra o
critério escrito, e o critério tem que ser **citado** no fechamento. "Achei que
não precisava" não é verificação — é a mesma classe de erro do LEARNING-0002
(premissa assumida em silêncio), agora aplicada a processo em vez de escopo.

## Regra criada no CLAUDE.md

> **DoD se verifica contra critério escrito, não de memória:** ao fechar uma
> tarefa, o item de ADR é resolvido consultando a lista "Quando um ADR é
> OBRIGATÓRIO" de `docs/adr/README.md`, e o fechamento **cita o critério** que
> se aplicou (ou registra por escrito por que nenhum se aplica). Decisão
> descrita apenas na seção de execução de um card **não** conta como ADR:
> card é registro de trabalho, ADR é registro de decisão.

Adicionada à seção "Definition of Done" do CLAUDE.md.
