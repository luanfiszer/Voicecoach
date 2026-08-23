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
| Q7 | O que `Protocol` faz que dispensa um framework de mock, e **em que momento** se descobre que um fake não satisfaz a porta? | CARD-004 | 2026-08-17 | reapresentada no CARD-007; **sem resposta e sem dispensa** |
| Q9 | Igualdade de `@dataclass`: por que dois objetos da mesma entidade com um campo diferente não são iguais, e por que o Python **proíbe** usá-los como chave de dict/set? | CARD-005 | 2026-08-18 | reapresentada no CARD-007; **sem resposta e sem dispensa** |

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

> **CARD-007 (2026-08-21): a fila FOI reapresentada na abertura**, antes do
> plano — Q7 e Q9, com o motivo de cada uma tocar aquele card (o primeiro fake
> cuja assinatura devolve `AsyncIterator`; a comparação de listas de eventos por
> igualdade estrutural). O desenvolvedor não respondeu nenhuma das duas e, no
> meio da sessão, pediu explicitamente que não houvesse mais perguntas. **Não
> foram fechadas por explicação do agente** (LEARNING-0004): seguem aqui, e
> abrem o CARD-008.
>
> Ironia útil, de novo: naquela mesma sessão as duas se demonstraram sozinhas.
> O `mypy` reprovou **três** vezes um dublê que tinha "tudo o que se lê" mas não
> satisfazia o `Protocol` — atributo onde o Protocol declarava `@property`, e
> membro invariante onde a covariância era necessária (Q7). E o teste do fluxo
> assere uma **lista inteira de eventos** com um `==` só, o que só funciona
> porque `frozen=True` gera `__eq__` por valor **e** `__hash__` (Q9). A
> demonstração existe; a resposta do desenvolvedor, não.

> **CARD-008 (2026-08-23): a fila FOI reapresentada na abertura**, antes do
> plano — Q7 e Q9, com o motivo de cada uma tocar aquele card (duas portas novas
> e seus fakes; a comparação de coleções de trechos). **Nenhuma das duas foi
> respondida nem dispensada**, e a sessão seguiu a pedido do desenvolvedor
> ("termine o que falta"). Seguem aqui: silêncio não é dispensa, e explicação do
> agente não fecha item (LEARNING-0004).
>
> **Q11 nasceu naquela sessão, e nasceu certa:** foi feita **antes** de o adapter
> de storage existir, sobre consequência observável. Também não foi respondida.
> O agente a demonstrou com execução — `put_object` chamado direto de uma
> corrotina congelou o event loop por 122 ms, com o heartbeat de 10 ms rodando
> **zero** voltas; em executor, 10 voltas e 1 ms de atraso máximo. A demonstração
> virou o teste `test_o_upload_nao_bloqueia_o_event_loop` e o ADR-0034. **A
> resposta do desenvolvedor continua faltando, e é ela que fecha o item.**
>
> Padrão que já é o quarto: as perguntas se demonstram sozinhas durante a
> implementação, e o item segue vermelho — o mecanismo produz **evidência**, mas
> a verificação de aprendizado depende de uma resposta que não vem. Se isso se
> repetir no CARD-009, vale um postmortem sobre a regra, não sobre a sessão.

## Fechadas

| # | Pergunta | Fechada em | Como |
|---|---|---|---|
| Q3 | Contrato de **dependência** vs. contrato de **direção** no import-linter: em que cenário só o segundo pega a violação? | 2026-08-19 (CARD-006) | Perguntada **antes** de escrever as listas `forbidden` dos módulos de STT. Primeira resposta parcialmente errada ("A quebra o forbidden"): a violação A — `from faster_whisper import ...` em `application`, com o módulo fora da lista — passou **verde**, `4 kept, 0 broken`. Demonstrado o par completo (mesma linha, com o módulo na lista → `BROKEN`) e **reformulado** uma vez. Respondida corretamente: apagando os contratos `forbidden`, só o `layers` quebra, e **nenhuma lista o torna redundante** — `layers` opera sobre o grafo interno sem lista, `forbidden` é o único que enxerga biblioteca de terceiros |
| Q10 | `jiter.from_json(buf, partial_mode=True)` sobre `b'{"spoken_reply": "Hi there, how ar'`: o que devolve, e por que isso mataria a cascata? | 2026-08-21 (CARD-007) | Perguntada **antes** de escrever o parser incremental. Primeira resposta **errada** (`{'spoken_reply': 'Hi there, how ar'}` — que é o que o `trailing-strings` devolve, não o `True`). Demonstrada com as três chamadas no terminal: `trailing-strings` → a string incompleta vem; `True` → `{}`; sem `partial_mode` → `ValueError: EOF while parsing a string`. Explicado o porquê (`True` só entrega valores **completos**, e uma string sem a aspa de fechamento não é um) e a consequência: a fala só apareceria quando estivesse inteira, que é esperar o objeto fechar — o card falhando em silêncio. **Reformulada uma vez** (quais trechos podem ir ao TTS com `"Hi there. How are yo"`) e **respondida corretamente**: só `"Hi there."`, porque só o que tem delimitador **e texto depois** está provadamente fechado |
| Q8 | Que falha o `lint-imports` **não** pega com a lista `forbidden` desatualizada? | 2026-08-18 (CARD-005) | Perguntada **no ponto da decisão**, antes de adicionar `sqlalchemy`. Primeira resposta errada ("o contrato de layers pega"); demonstrada com a violação injetada (`4 kept, 0 broken` com a violação dentro → `BROKEN` depois de atualizar a lista); **reformulada** e respondida corretamente: gate verde significa "nenhuma violação **entre as que eu listei**" |
