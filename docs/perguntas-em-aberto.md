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
| Q4 | `@lru_cache` em `get_settings()`: o que exatamente fica em cache, e por que isso morde na suíte de testes? | CARD-002 | 2026-08-17 | "não sei responder" |
| Q5 | Por que o hook de `mypy` usa `pass_filenames: false`? | CARD-003 | 2026-08-17 | dispensada, sem resposta |
| Q6 | Por que o limiar de cobertura é travado no valor real de hoje em vez de num número redondo? | CARD-003 | 2026-08-17 | dispensada, sem resposta |
| Q7 | O que `Protocol` faz que dispensa um framework de mock, e **em que momento** se descobre que um fake não satisfaz a porta? | CARD-004 | 2026-08-17 | **dispensada pelo dev** no CARD-006 |
| Q9 | Igualdade de `@dataclass`: por que dois objetos da mesma entidade com um campo diferente não são iguais, e por que o Python **proíbe** usá-los como chave de dict/set? | CARD-005 | 2026-08-18 | explicada com execução; não reformulada por falta de orçamento de perguntas da sessão |

> **Q7** foi reapresentada na abertura do CARD-006 e **dispensada pelo
> desenvolvedor** ("vamos pular essas perguntas e finalizar a implementação").
> Continua aqui. Ironia útil: naquela mesma sessão o mecanismo se demonstrou
> sozinho — um fake com o primeiro parâmetro renomeado passou no `pytest` e foi
> reprovado pelo `mypy`. A demonstração existe; a resposta do desenvolvedor,
> não, e é ela que fecha o item (LEARNING-0004). Volta no CARD-007.
>
> **Q9** não foi feita no CARD-006: não houve decisão de igualdade de
> `@dataclass` naquele card (a porta devolve `Transcript`, que é lido e não
> comparado). Segue na fila.
>
> **CARD-018 (2026-08-19): a fila não foi reapresentada na abertura** — o agente
> leu o caminho errado, concluiu que este arquivo não existia e registrou isso no
> card. Q9 era especialmente relevante (o card exercita igualdade de `@dataclass`
> na comparação da coleção de trechos). **Q3, Q7 e Q9 são as que tocam o
> CARD-006** e têm de abrir aquela sessão.

## Fechadas

| # | Pergunta | Fechada em | Como |
|---|---|---|---|
| Q3 | Contrato de **dependência** vs. contrato de **direção** no import-linter: em que cenário só o segundo pega a violação? | 2026-08-19 (CARD-006) | Perguntada **antes** de escrever as listas `forbidden` dos módulos de STT. Primeira resposta parcialmente errada ("A quebra o forbidden"): a violação A — `from faster_whisper import ...` em `application`, com o módulo fora da lista — passou **verde**, `4 kept, 0 broken`. Demonstrado o par completo (mesma linha, com o módulo na lista → `BROKEN`) e **reformulado** uma vez. Respondida corretamente: apagando os contratos `forbidden`, só o `layers` quebra, e **nenhuma lista o torna redundante** — `layers` opera sobre o grafo interno sem lista, `forbidden` é o único que enxerga biblioteca de terceiros |
| Q8 | Que falha o `lint-imports` **não** pega com a lista `forbidden` desatualizada? | 2026-08-18 (CARD-005) | Perguntada **no ponto da decisão**, antes de adicionar `sqlalchemy`. Primeira resposta errada ("o contrato de layers pega"); demonstrada com a violação injetada (`4 kept, 0 broken` com a violação dentro → `BROKEN` depois de atualizar a lista); **reformulada** e respondida corretamente: gate verde significa "nenhuma violação **entre as que eu listei**" |
