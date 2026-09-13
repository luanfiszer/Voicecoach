# LEARNING-0007 — O relato dizia "recomeçar", e a investigação mapeou um gesto só

- **Data:** 2026-09-12
- **Card/sessão relacionado:** CARD-042 (investigação de 2026-09-09 → execução no
  iPhone em 2026-09-12)

## Sintoma

O CARD-042 nasceu de um relato do primeiro uso real: *"ao errar a gravação e
tentar recomeçar, o app continua falando"*. A investigação de 2026-09-09 afirmou
que as peças **já estavam ligadas** e apontou `TelaConversa.tsx:86` — o botão de
gravar chama `turno.limpar()` antes de `gravacao.iniciar()`.

A correção do mecanismo (`pause()` antes de `remove()`) fez o **botão** calar o
professor, e isso foi medido. Mas no aparelho, durante o teste, o desenvolvedor
relatou:

> *"Apenas quando eu clico no regravar ele libera o botão mas não para o turno."*

O link **"regravar"** chamava só `gravacao.descartar`. O card — cujo **título** é
*"Regravar cala o professor"* — teria fechado verde com o gesto do próprio título
ainda quebrado.

## Causa raiz

**O relato foi traduzido para um caminho de código lendo código, e não
reproduzindo o gesto.** A pergunta feita foi *"onde a gravação recomeça?"*, e ela
tem uma resposta no código. Mas a tela tem **dois** controles que a palavra
"recomeçar" pode nomear:

| Controle | O que fazia |
|---|---|
| botão principal — *"Toque para gravar de novo"* | `turno.limpar()` → `gravacao.iniciar()` |
| link **"regravar"** | `gravacao.descartar()` — **só** |

A investigação mapeou o primeiro e declarou o bug entendido. O card até dizia
*"começa reproduzindo, não corrigindo"* — mas a reprodução planejada era a do
caminho **mapeado** (*dedo no botão → `limpar()` → `remove()`*), não a do gesto
**relatado**. **Reproduzir a hipótese não é reproduzir o relato.**

Agravante: a divergência estava visível no próprio card. O título nomeava o link
("Regravar"); o texto apontava o botão.

## Como descobri

No teste 1 no iPhone (2026-09-12), o pedido era interromper o professor tocando
em gravar. O desenvolvedor usou também o "regravar" e notou a diferença. O código
confirmou em uma linha: `onPress={gravacao.descartar}`.

Corrigido por decisão do desenvolvedor (`turno.limpar()` antes de
`gravacao.descartar()`) e medido no aparelho com um instrumento temporário:
`geração 3 · 1 calado(s) · avanço +300ms: [1] ms`.

## Como evitar

Antes de mapear o código de um relato de uso, **liste todo controle da tela que
as palavras do relato podem nomear** e reproduza cada um, no ambiente onde o
relato aconteceu — o gesto literal primeiro, a hipótese depois. Um plano de
reprodução que começa numa linha de código já escolheu o caminho, e o que ele
não escolheu fica sem teste.

## Regra criada no CLAUDE.md

> **Bug relatado por uso se reproduz pelo gesto, não pelo código** (origem:
> [LEARNING-0007]): antes de mapear o caminho de código de um relato ("ao tentar
> recomeçar…"), liste **todo controle da tela que as palavras do relato podem
> nomear** e reproduza cada um no ambiente onde o relato aconteceu. Reproduzir a
> hipótese não é reproduzir o relato: um plano que começa numa linha de código já
> escolheu o caminho.
