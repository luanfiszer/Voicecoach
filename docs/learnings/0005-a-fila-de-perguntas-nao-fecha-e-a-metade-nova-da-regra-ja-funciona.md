# LEARNING-0005 — A fila de perguntas não fecha, e a metade nova da regra já funciona

- **Data:** 2026-08-26
- **Card/sessão relacionado:** abertura do CARD-013; série de CARDs 005–012
  (oito sessões consecutivas com o item vermelho pelo mesmo motivo)

## Sintoma

O LEARNING-0004 reescreveu a regra do explicador em duas metades:

1. **perguntar no ponto da decisão**, sobre consequência observável, dentro da
   sessão;
2. **a fila** (`docs/perguntas-em-aberto.md`): pergunta não fechada é
   reapresentada na abertura da sessão seguinte, até fechar.

Oito sessões depois, as duas metades têm resultados opostos, e o registro é
inequívoco porque cada sessão anotou o desfecho.

**A metade 1 funciona.** As perguntas feitas no ponto da decisão fecham:

| Sessão | Pergunta nova | Desfecho |
|---|---|---|
| CARD-005 | Q8 — o que o `lint-imports` **não** pega com a lista `forbidden` desatualizada | 1ª errada, demonstrada com a violação injetada, **reformulada, respondida** |
| CARD-006 | Q3 — contrato de dependência vs. de direção | 1ª parcialmente errada, demonstrado o par completo, **reformulada, respondida** |
| CARD-007 | Q10 — `jiter` com `partial_mode` sobre JSON truncado | 1ª errada, demonstradas as três chamadas, **reformulada, respondida** |
| CARD-012 | P1 — o host na assinatura SigV4 | 1ª errada, três execuções contra o MinIO, **reformulada, respondida** |
| CARD-012 | P2 — um player por trecho vs. `replace(url)` | **respondida na primeira** |

**A metade 2 nunca fechou uma pergunta sequer.** A fila tem 11 abertas. Q7 foi
reapresentada em **sete** aberturas (CARDs 006, 007, 008, 009, 010, 011, 012);
Q9 em cinco; Q11 em quatro. Nenhuma foi respondida. Duas (Q5, Q6) foram
dispensadas. Em zero ocasiões a reapresentação produziu uma resposta.

O resultado combinado: o item da DoD fecha **vermelho** há oito sessões, mesmo
nas sessões em que a metade que funciona funcionou perfeitamente — o CARD-012
fez duas perguntas no ponto da decisão, fechou as duas com execução como
testemunha, e ainda assim o item foi registrado como vermelho por causa da fila
antiga.

## Causa raiz

**A fila depende, para fechar, exatamente do recurso que ela é incapaz de
produzir: a atenção do desenvolvedor num momento em que ele não escolheu estudar
aquilo.**

Três razões empilhadas, e a terceira é a que a torna insalvável na forma atual.

### 1. A pergunta reapresentada perdeu o contexto que a tornava respondível

O LEARNING-0004 diagnosticou que perguntar **no fim** não funciona porque o
contexto esfriou. A fila reintroduz o mesmo defeito com outro nome: uma pergunta
sobre `@lru_cache` nascida no CARD-002 é reapresentada no CARD-011, um card de
front-end, onde nada no ecrã do desenvolvedor tem a ver com ela. A abertura de
sessão é o momento **mais frio possível** para uma decisão de dez cards atrás.
O CARD-011 registra isso com honestidade: a fila é toda de backend e o card era
de cliente, e as perguntas entraram "por paralelo".

### 2. As perguntas da fila já foram respondidas — pela execução, não pelo dev

Q7, Q9 e Q11 se demonstraram **sozinhas**, com evidência, em sete sessões
seguidas: o `mypy` reprovando fakes no instante em que uma porta ganha método
(Q7, seis ocorrências registradas); testes comparando listas inteiras de eventos
com um `==` só, que só funciona por `frozen=True` (Q9); o `put_object` síncrono
congelando o event loop por 122 ms com o heartbeat em zero voltas, que virou o
ADR-0034 e um teste (Q11). O conhecimento que a pergunta queria verificar está
no repositório, com teste que o segura. O que falta é a **formalidade da
resposta** — e é só a formalidade que a fila cobra.

### 3. Um item que nunca pode ficar verde não governa nada

É o mesmo defeito do LEARNING-0004, invertido. Lá, o item nunca ficava vermelho
porque o agente o fechava sozinho. Aqui, ele nunca pode ficar verde: uma sessão
perfeita pela metade 1 continua vermelha pela metade 2, e o custo de zerar a
fila é responder onze perguntas frias de uma vez, o que nenhuma sessão vai fazer.

Um sinal que está sempre aceso não é sinal — é ruído. E o preço é real: o
vermelho permanente **encobre** a informação que interessa, que é se as perguntas
**desta** sessão fecharam. No CARD-012 essa informação existia e era ótima, e
ficou escondida atrás do mesmo vermelho de sempre.

## Como descobri

1. A pendência foi levantada pelo próprio agente na abertura do CARD-009 como
   "proposta de postmortem sobre a regra, não sobre a sessão", e reapresentada
   nas aberturas dos CARDs 010, 011, 012 e 013 — cinco vezes sem decisão, porque
   **reescrever uma regra da constituição é decisão do desenvolvedor**, não do
   agente.
2. Leitura em série do `docs/perguntas-em-aberto.md`: os blocos de nota por card
   são o registro de oito reapresentações e zero fechamentos. Como no
   LEARNING-0004, **o padrão só é visível na série** — cada sessão isolada
   parecia um adiamento razoável.
3. Separar as duas metades e tabelar cada uma. Feito isso, a assimetria é
   gritante: 5 de 5 perguntas do ponto da decisão fecharam; 0 de 11 da fila.
4. Decisão do desenvolvedor na abertura do CARD-013, cobrada com os três
   caminhos por escrito (manter e responder / reescrever / manter e aceitar o
   vermelho): **reescrever a regra**.

## Como evitar

**Manter a metade que funciona e parar de cobrar a que não funciona.**

1. **O item da DoD passa a ser sobre as perguntas DESTA sessão.** Ele fica verde
   quando cada pergunta feita no ponto da decisão teve desfecho registrado
   (respondida / dispensada por mim). É verificável, é local, e é o que o
   LEARNING-0004 quis dizer.
2. **A fila deixa de ser dívida cobrável e vira arquivo.** As 11 perguntas
   abertas passam para uma seção **"Arquivadas"**, com o registro do que a
   execução demonstrou sobre cada uma e o commit/teste que serve de testemunha.
   Nada se apaga: o histórico é o que prova que o mecanismo novo é melhor que o
   antigo — que é literalmente o que o cabeçalho do arquivo já pedia.
3. **A reapresentação na abertura continua existindo, mas encolhe e muda de
   critério:** só volta pergunta feita **na sessão imediatamente anterior** e que
   ficou sem desfecho. Uma sessão de distância ainda é contexto quente; dez não
   são. Sem resposta na segunda apresentação, ela é arquivada com o que a
   execução demonstrou — e não fica pendurada para sempre.
4. **Uma pergunta arquivada pode voltar**, e o gatilho é objetivo: quando um card
   novo tocar de novo a mesma decisão, ela é refeita **no ponto da decisão
   daquele card** — que é onde ela nasceu certa da primeira vez.

O que **não** muda, e é o coração da regra: no máximo 2 perguntas por sessão, no
ponto da decisão, sobre consequência observável, conferidas rodando o comando na
hora, e **fechadas pelo desenvolvedor, nunca pelo agente**. O LEARNING-0004
continua valendo por inteiro nesse ponto.

## Regra criada no CLAUDE.md

Substitui os dois últimos parágrafos da seção **"A regra do explicador"** (o item
3 e o parágrafo da fila) e ajusta o item correspondente da **Definition of
Done** — consolidação, não regra a mais.

> **3. Quem fecha o item sou eu, não o agente.** Três desfechos, e o agente
> registra no card o que de fato ocorreu:
>
> - **respondida** → item verde;
> - **errada ou "não sei"** → o agente explica e **reformula a pergunta na mesma
>   sessão**, uma vez. Se ainda assim não fechar, ela volta **uma** vez, na
>   abertura da sessão seguinte;
> - **dispensada por mim** → registrada como **"dispensado pelo desenvolvedor"**,
>   nunca como cumprida nem como "parcial".
>
> **4. O item da DoD é sobre as perguntas DESTA sessão** (origem:
> [LEARNING-0005]). Ele fica verde quando cada pergunta feita no ponto da decisão
> teve desfecho registrado. Pergunta antiga **não** o mantém vermelho: um item
> que nunca pode ficar verde não governa nada — é o defeito do LEARNING-0004 de
> cabeça para baixo.
>
> **5. A fila é arquivo, não cobrança.** `docs/perguntas-em-aberto.md` guarda o
> histórico e o que a execução demonstrou sobre cada pergunta. Só é
> **reapresentada** na abertura a pergunta da sessão **imediatamente anterior**
> que ficou sem desfecho; sem resposta na segunda vez, é arquivada com a
> evidência. Pergunta arquivada volta quando um card novo tocar a mesma
> decisão — refeita **no ponto da decisão daquele card**, que é onde ela nasceu
> certa.

E, na Definition of Done, o item passa a ser:

> - [ ] A **regra do explicador** foi cumprida **nesta sessão**: cada pergunta
>       feita no ponto da decisão tem desfecho registrado no card (respondida /
>       dispensada por mim). Item fechado pelo agente com a própria explicação
>       **não** conta (origem: [LEARNING-0004]). A fila de
>       `docs/perguntas-em-aberto.md` é arquivo e **não** mantém este item
>       vermelho (origem: [LEARNING-0005]).
