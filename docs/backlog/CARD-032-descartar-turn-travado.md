# CARD-032 — "Descartar": a ação do aluno sobre o turn que travou

- **ID:** CARD-032
- **Épico:** Fase 3 — Domínio pedagógico (backend do artboard 16)
- **Plataforma:** backend · **Esforço:** P · **Status:** backlog
- **Dependências:** CARD-025; ADR-0023, ADR-0037, ADR-0039

## Contexto

Backend da metade inferior do artboard 16 — *"Demorou mais que o normal. Sua
fala foi enviada, mas a resposta não chegou em 30s"* — com dois botões:
**Tentar de novo** e **Descartar**.

É o **achado #6** da `reconciliacao-telas-dominio.md`, registrado em 2026-08-18
como *"não previsto por nenhum card"* e órfão desde então. O CARD-025 entrega
metade dele (o servidor marca `failed` sozinho); a outra metade — **o aluno
decidindo** — nunca teve dono.

## Problema

**Os dois botões do artboard não existem no contrato, e um deles pode não dever
existir.**

- **"Tentar de novo"** parece pedir reprocessamento — e o ADR-0037 **proíbe**
  reprocessar depois de entrega parcial, porque o aluno já ouviu frases que ele
  ouviria de novo. Antes de qualquer trecho, retentar é legítimo. Depois, não é.
  O botão só é honesto se souber em qual dos dois casos está.
- **"Descartar"** não tem significado definido. A `reconciliacao` já anotava a
  pergunta e ela continua aberta: o turn some da tela, é apagado no servidor, ou
  nunca existiu?

## Requisitos funcionais

- **RF1 — DECIDIDO (2026-08-27): "Descartar" some da tela e não apaga nada.**
  O turn permanece `failed` no servidor, no histórico e nas agregações. Duas
  consequências que seguem direto disso:
  - **nada é destruído** ⇒ **não há ADR** (o critério 4 não se aplica: nenhum
    dado do aluno é apagado), o endpoint não é destrutivo e o card fica **P**;
  - **se a fala nunca subiu** (fila offline), o descarte é **puramente local** —
    apagar o arquivo do aparelho, sem tocar no servidor. Esse caminho é do
    CARD-027 e nem chega aqui.

  Fica então a pergunta que decide se este card existe: **o servidor precisa
  saber que o aluno descartou?** Se o turn já é `failed` e continua no
  histórico, "descartar" pode ser inteiramente um gesto de UI. Ver o Risco
  abaixo — é a primeira coisa a resolver no plano.
- **RF2** — Descartar é possível **apenas** em turn não concluído. Turn
  `completed` não é descartável — o aluno já recebeu o que pediu, e apagar
  resposta entregue é outra conversa (direito de exclusão, CARD-017).
- **RF3** — Descartar um turn **parcialmente entregue** é permitido, e **não**
  apaga os trechos já ouvidos se a decisão for (a).
- **RF4** — Nenhuma mídia é removida por descarte. A retenção do CARD-017
  continua sendo a única coisa que apaga áudio, no prazo dela.
- **RF5** — "Tentar de novo" **não** existe como reprocessamento de turn. Se o
  aluno quiser tentar de novo, ele grava de novo: é um turn novo, com
  `Idempotency-Key` nova. O botão do artboard vira, no cliente, "gravar de novo"
  — e o card registra que essa foi a decisão, para o desenho não voltar.
- **RF6** — Descartar um turn **que estava só lento e conclui logo depois** não
  pode ressuscitá-lo na tela nem perder a resposta em silêncio. O desfecho é
  definido, não acidental.

## Requisitos não funcionais

- **RNF1 — Idempotente.** Descartar duas vezes é o mesmo que uma. A fila offline
  e o botão nervoso garantem que isso vai acontecer.
- **RNF2 — Autorização, mesmo sem auth.** Hoje o `Student` vem de seed
  (`DEV_STUDENT_ID`), mas o endpoint nasce verificando que o turn pertence ao
  aluno da requisição — o dia em que a auth entrar (Fase 3) não pode ser o dia
  em que se descobre que qualquer um descarta o turn de qualquer um.
- **RNF3 — Sem ação destrutiva no contrato.** A decisão do RF1 tirou o critério
  4 da mesa. Se em algum momento alguém propuser apagar de verdade, isso é card
  novo com ADR, não uma extensão silenciosa deste.
- **RNF4 — As agregações não mudam.** O turn descartado continua contando no
  CARD-030, no resumo do CARD-031 e na cota do CARD-015 — porque ele de fato
  aconteceu e de fato custou.
- **RNF5 — O `UsageEvent` NÃO é apagado** em nenhuma das hipóteses. O custo foi
  pago ao provedor: apagá-lo faria o caixa mentir, e o ADR-0051 pôs o
  `UsageEvent` fora do agregado exatamente para que o ciclo de vida do turn não
  arrastasse o registro financeiro.
- **RNF6 — A corrida do RF6 é real.** Descarte e conclusão do worker podem
  chegar no mesmo segundo. Teste com concorrência de verdade, não sequencial.

## Escopo

- **In:** a decisão do RF1 registrada; o endpoint de descarte com o efeito
  decidido; a guarda do RF2; o teste de corrida do RF6; o registro escrito do
  RF5.
- **Out:** o overlay e os botões (CARD-027); a varredura automática de travados
  (CARD-025 — este card é a ação **manual**, e as duas coexistem); o direito de
  exclusão de conta inteira (CARD-017 / LGPD).

## Critérios de aceite

- **Dado** um turn `processing` há mais que o prazo, **quando** o aluno
  descarta, **então** o turn continua existindo no banco e continua aparecendo
  no histórico — o descarte não o remove.
- **Dado** um turn `completed`, **quando** tento descartar, **então** recebo
  Problem Details recusando, e nada muda.
- **Dado** um turn com 2 trechos entregues, **quando** descarto, **então** os
  trechos permanecem (se (a)) e `delivered_partially` continua verdadeiro.
- **Dado** dois descartes concorrentes, **então** o resultado é o mesmo de um.
- **Dado** um descarte concorrente com a conclusão do worker, **então** o
  desfecho é o que foi decidido — e o teste diz qual, em vez de aceitar
  qualquer um dos dois.
- **Dado** qualquer descarte, **então** o `UsageEvent` do turn continua no banco.

## Riscos

- **O card pode não precisar existir, e isso é o primeiro a verificar.** Com a
  decisão do RF1, "descartar" talvez seja só o app parando de mostrar um turn
  que já está `failed`. O que ainda pode justificar um endpoint é o RF6 (o turn
  lento que conclui **depois** do descarte: sem registro no servidor, a resposta
  volta a aparecer). **Se o plano concluir que não há trabalho de backend, o
  card morre e o comportamento inteiro vai para o CARD-027** — matar um card por
  ter sido decidido é resultado legítimo, não fracasso.
- **"Tentar de novo" pode voltar pela porta dos fundos.** O RF5 fecha isso por
  escrito porque, sem registro, o próximo card de UI reintroduz o botão a partir
  do PNG.

## Objetivo de aprendizado

Como se testa corrida de verdade em `pytest` async — `asyncio.gather` sobre duas
chamadas que disputam a mesma linha, e por que um teste sequencial disfarçado
passa exatamente no bug que ele deveria pegar. É a mesma armadilha do
get-then-set, e não há `lock` de aplicação para salvar: quem arbitra é o banco.
