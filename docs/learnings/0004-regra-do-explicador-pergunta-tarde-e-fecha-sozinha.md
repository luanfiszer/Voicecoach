# LEARNING-0004 — A regra do explicador pergunta tarde demais e o agente fecha o item sozinho

- **Data:** 2026-08-18
- **Card/sessão relacionado:** CARDs 001, 002, 003 e 004 (quatro ocorrências
  consecutivas); gatilho aberto no fechamento do CARD-003 e reaberto no PR #6

## Sintoma

O único item da Definition of Done que existe para garantir o produto declarado
do projeto — o conhecimento do desenvolvedor — **nunca fechou por verificação**.
Quatro sessões, quatro desfechos diferentes, nenhum verde:

| Card | O que aconteceu | Como o item foi fechado |
|---|---|---|
| 001 | 2 perguntas feitas (`src/` layout; `api \| worker` na mesma camada) | Dev pediu a explicação em vez de responder → "caminho alternativo" |
| 002 | 2 perguntas feitas (contrato novo do import-linter; `@lru_cache`) | **"não sei responder"** → "caminho alternativo" |
| 003 | 2 perguntas feitas (`pass_filenames: false`; limiar de cobertura) | Dev **não respondeu**, pediu para seguir → dispensado |
| 004 | 2 perguntas feitas (`Protocol` vs. Moq; `forbidden` desatualizada) | 1 resposta **errada** (falou de CORS) + 1 "não sei dizer" → explicado com demo, marcado **parcial** |

Citação do próprio CARD-003 (l. 321–328): *"É a terceira vez seguida. Três
ocorrências não são coincidência — a regra do explicador, como está escrita, não
está produzindo o que o CLAUDE.md diz ser o produto do projeto."* O CARD-004
repetiu o padrão e apenas trocou o rótulo de "cumprido pelo caminho alternativo"
para "parcial".

Agravante registrado no CARD-003 (l. 330–332): uma das perguntas partia de uma
**leitura errada da saída do `mypy` pelo próprio agente** — a pergunta estava
mal formulada antes de o desenvolvedor ter chance de errá-la.

## Causa raiz

Duas causas empilhadas. A segunda é a que explica por que nada mudou em quatro
sessões.

### 1. A pergunta chega no momento em que ela não pode funcionar

A regra manda perguntar **"ao final de qualquer implementação"**, sobre código
que o agente escreveu e já explicou em prosa. Nesse ponto:

- o desenvolvedor foi **leitor** da implementação, não autor — não teve nenhum
  momento de produzir uma previsão, uma decisão ou uma tentativa de resposta
  **antes** de a explicação existir;
- a decisão que a pergunta cobra foi tomada dezenas de mensagens antes, no meio
  de um bloco grande de trabalho — o contexto já esfriou;
- a sessão está longa e o incentivo é fechar, não estudar (foi literalmente o
  que aconteceu no CARD-003).

"Não sei" nesse arranjo **não é sinal de falha do desenvolvedor: é o resultado
esperado do desenho.** É exame sem estudo, sobre matéria que o aluno assistiu
alguém resolver. O que produz retenção é recuperação ativa **antes** da
explicação e no ponto da decisão; a regra faz o oposto — explica primeiro,
pergunta depois, no fim.

### 2. O item tem uma saída que o próprio agente pode acionar sozinho

O texto atual oferece o "caminho alternativo": *"reescreva de forma mais simples
ou me explique até eu conseguir defender aquele código em uma entrevista
técnica"*. Consequências:

- o critério de saída (**"até eu conseguir defender"**) **não tem teste** — não
  há nada que torne a condição observável, então quem declara o fim é quem
  explicou;
- por isso o agente fecha o item **unilateralmente**, escrevendo mais prosa. Em
  4 de 4 sessões foi exatamente o que aconteceu;
- um item de DoD que **nunca fica verde por verificação e nunca fica vermelho**
  não governa nada: vira formulário. O rótulo "parcial" do CARD-004 é o
  reconhecimento honesto disso, não a correção do problema.

**A raiz em uma frase:** a regra terceiriza a verificação do aprendizado para o
mesmo agente que produziu o código e a explicação, num momento em que a resposta
correta do desenvolvedor é estatisticamente improvável — e depois aceita a
explicação como prova de que o aprendizado ocorreu.

## Como descobri

1. Instrução direta do desenvolvedor no prompt do CARD-005: rodar `/postmortem`
   sobre o próprio mecanismo antes de implementar.
2. `grep -n -A 30 "explicador" docs/backlog/CARD-00*.md` — os quatro
   fechamentos lado a lado. O padrão só é visível na série; **cada card
   isolado parecia um caso honesto e justificado**, com registro explícito do
   desvio. Foi a honestidade do registro card a card que tornou a série
   auditável — e foi a leitura em série que mostrou que o desvio era o
   comportamento normal do mecanismo, não a exceção.
3. Leitura do texto da regra no `CLAUDE.md` procurando **qual condição fecha o
   item** — e a constatação de que a condição ("até eu conseguir defender") não
   é observável por ninguém, muito menos verificável pelo agente.

## Como evitar

Três mudanças no mecanismo, todas na direção de tirar a verificação das mãos do
agente e movê-la para onde ela ainda é barata:

1. **Perguntar no ponto da decisão, não no fim.** Antes de escrever a peça que
   carrega uma decisão não-óbvia, uma pergunta curta de previsão ("o que você
   acha que acontece se…"), e só então implementar e explicar. Recuperação ativa
   antes da explicação, com o contexto quente.
2. **Perguntar sobre consequência observável, não sobre conceito.** "O que
   quebra e com que mensagem se eu remover X?" tem resposta conferível rodando
   o comando na hora. Errar vira demonstração, não constrangimento — e o agente
   não pode errar a premissa da pergunta sem que a execução o denuncie (o que
   aconteceu no CARD-003).
3. **Fechamento com dono explícito.** O agente não fecha o item. Ou o
   desenvolvedor responde (verde), ou **ele** dispensa — e nesse caso o item é
   registrado como **dispensado pelo desenvolvedor**, com a pergunta indo para
   uma fila reapresentada na abertura da sessão seguinte. Dívida de aprendizado
   passa a ser cobrada no **começo** de uma sessão (fresca), não no fim de uma
   longa.

## Regra criada no CLAUDE.md

Substitui integralmente a seção **"A regra do explicador"** e ajusta o item
correspondente da **Definition of Done** — consolidação, não regra a mais.

> ## A regra do explicador
>
> O produto deste projeto é o meu conhecimento; o código é subproduto. A regra
> abaixo existe para verificar isso — e verificação que o agente pode fechar
> sozinho não é verificação (origem: [LEARNING-0004]).
>
> **1. Perguntar no ponto da decisão, não no fim.** Quando a implementação
> chegar a uma decisão não-óbvia (uma dependência nova, uma fronteira, um
> idioma de Python sem paralelo em C#, um gate que passa a morder), o agente
> **para antes de escrever o código** e faz **uma** pergunta curta de previsão:
> *"o que você acha que acontece se…"*. Só depois implementa e explica. São no
> máximo 2 dessas por sessão — as duas decisões mais caras de errar.
>
> **2. A pergunta é sobre consequência observável.** Preferir *"o que quebra, e
> com que mensagem, se eu remover X?"* a *"o que é Y?"*. Sempre que possível a
> resposta é conferida rodando o comando na hora: errar vira demonstração com
> evidência, e uma pergunta mal formulada pelo agente é desmascarada pela
> execução.
>
> **3. Quem fecha o item sou eu, não o agente.** Três desfechos possíveis, e o
> agente registra o que de fato ocorreu:
> - **respondida** → item verde;
> - **errada ou "não sei"** → o agente explica e **reformula a pergunta na
>   mesma sessão**, uma vez. Se ainda assim não fechar, vira dívida (abaixo);
> - **dispensada por mim** → item registrado como **"dispensado pelo
>   desenvolvedor"**, nunca como cumprido nem como "parcial".
>
> Pergunta não fechada vira linha em `docs/perguntas-em-aberto.md` (pergunta,
> card de origem, data) e é **reapresentada na abertura da próxima sessão**,
> antes do plano. Dívida de aprendizado se cobra no começo de uma sessão, não
> no fim de uma longa.

E, na Definition of Done, o item passa a ser:

> - [ ] A **regra do explicador** foi cumprida, com o desfecho de cada pergunta
>       registrado no card (respondida / dispensada por mim / em aberto). Item
>       fechado pelo agente com a própria explicação **não** conta.
