# Perguntas em aberto — dívida de aprendizado

Fila da **regra do explicador** (CLAUDE.md, reescrita no CARD-005 —
[LEARNING-0004](learnings/0004-regra-do-explicador-pergunta-tarde-e-fecha-sozinha.md)).

Toda pergunta que não fechou na sessão de origem entra aqui e é
**reapresentada na abertura da próxima sessão**, antes do plano. Dívida de
aprendizado se cobra no começo de uma sessão fresca, não no fim de uma longa.

Ao fechar uma pergunta, mova a linha para "Fechadas" com a data e o desfecho —
o histórico é o que mostra se o mecanismo novo funciona melhor que o antigo.

## Abertas

O passivo abaixo veio dos CARDs 001–004, todos fechados pelo mecanismo antigo
(agente perguntava no fim e fechava o item com a própria explicação). São as
perguntas que nunca tiveram resposta verificada.

| # | Pergunta | Card de origem | Desde | Desfecho anterior |
|---|---|---|---|---|
| Q1 | Por que o `src/` layout muda o que é exercitado no teste local, e que classe de erro ele revela que a pasta plana esconde? | CARD-001 | 2026-08-17 | explicado, não respondido |
| Q2 | Por que `api` e `worker` são a **mesma** camada no contrato do import-linter, e que atalho concreto a seta proibida impede? | CARD-001 | 2026-08-17 | explicado, não respondido |
| Q3 | Contrato de **dependência** vs. contrato de **direção**: em que cenário só o segundo pega a violação? | CARD-002 | 2026-08-17 | "não sei responder" |
| Q4 | `@lru_cache` em `get_settings()`: o que exatamente fica em cache, e por que isso morde na suíte de testes? | CARD-002 | 2026-08-17 | "não sei responder" |
| Q5 | Por que o hook de `mypy` usa `pass_filenames: false`? | CARD-003 | 2026-08-17 | dispensada, sem resposta |
| Q6 | Por que o limiar de cobertura é travado no valor real de hoje em vez de num número redondo? | CARD-003 | 2026-08-17 | dispensada, sem resposta |
| Q7 | O que `Protocol` faz que dispensa um framework de mock, e **em que momento** se descobre que um fake não satisfaz a porta? | CARD-004 | 2026-08-17 | respondida errado (CORS) |
| Q9 | Igualdade de `@dataclass`: por que dois objetos da mesma entidade com um campo diferente não são iguais, e por que o Python **proíbe** usá-los como chave de dict/set? | CARD-005 | 2026-08-18 | explicada com execução; não reformulada por falta de orçamento de perguntas da sessão |

> **Q7** volta no CARD-006/007, onde nasce o primeiro *fake* de porta — este card
> testou adapters contra Postgres real, então não houve fake para exercitá-la.

## Fechadas

| # | Pergunta | Fechada em | Como |
|---|---|---|---|
| Q8 | Que falha o `lint-imports` **não** pega com a lista `forbidden` desatualizada? | 2026-08-18 (CARD-005) | Perguntada **no ponto da decisão**, antes de adicionar `sqlalchemy`. Primeira resposta errada ("o contrato de layers pega"); demonstrada com a violação injetada (`4 kept, 0 broken` com a violação dentro → `BROKEN` depois de atualizar a lista); **reformulada** e respondida corretamente: gate verde significa "nenhuma violação **entre as que eu listei**" |
