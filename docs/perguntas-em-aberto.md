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
| Q11 | Se eu chamar `client.put_object(...)` **direto dentro de uma corrotina**, o que acontece com as outras corrotinas do worker enquanto o upload corre — e como eu provaria isso num teste? | CARD-008 | 2026-08-23 | reapresentada no CARD-009; **sem resposta e sem dispensa** |
| Q12 | Contratos do import-linter, os dois lados: o `forbidden` segue **cadeias indiretas** (`use_case → encoding → av` reprova mesmo sem `import av` escrito) e o `layers` **só enxerga o grafo interno** (biblioteca externa é invisível para ele). Dado um import, quantos e quais contratos quebram? | CARD-009 | 2026-08-23 | feita no ponto da decisão; 1ª resposta errada (1, era 2), **reformulada uma vez**, 2ª também errada (2, era 1) |
| Q13 | Um gerador assíncrono não executa nada até o primeiro `__anext__`, então `events.subscribe(turn_id)` devolve o objeto **sem** ter emitido `SUBSCRIBE`. Se o caso de uso lê o banco antes de começar a iterar, e o worker publica o `chunk:0` exatamente nessa janela — o que o aluno vê na tela, e o que acontece com esse trecho? | CARD-010 | 2026-08-23 | feita **antes** de escrever o código, no ponto da decisão; **sem resposta e sem dispensa** |
| Q14 | Lendo `response.body` do SSE com o **`fetch` global do React Native** (não o `expo/fetch`): o stream chega em pedaços, chega inteiro só no fim, ou dá erro porque `body` não é stream? | CARD-011 | 2026-08-24 | feita **antes** de escrever o spike, no ponto da decisão de dependência; **sem resposta e sem dispensa** |

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

> **CARD-009 (2026-08-23): a fila FOI reapresentada na abertura** — Q7, Q9 e Q11,
> com o motivo de cada uma tocar aquele card (nove fakes de porta de uma vez; a
> comparação da lista inteira de eventos publicados com um `==` só; dois modelos
> de IA, um banco e um storage disputando o mesmo event loop). **Nenhuma das três
> foi respondida nem dispensada:** o desenvolvedor respondeu apenas as três
> decisões de escopo ("Vamos com A, incluir o list_by_session, Dockerfile em card
> próprio"). Silêncio não é dispensa (LEARNING-0004).
>
> As três se demonstraram sozinhas de novo, e agora com o teste como testemunha:
> **Q7** — o `mypy` reprovou **dois** fakes de storage no instante em que
> `MediaStorage` ganhou `get`, com o `pytest` verde; **Q9** — o teste
> `test_os_eventos_publicados_sao_exatamente_estes` compara seis eventos com um
> `==` só, o que só funciona porque `frozen=True` gera `__eq__` por valor;
> **Q11** — a resposta virou desenho: `AacAudioEncoder` empurra a codificação
> para um executor, com teste de heartbeat provando que o event loop não congela.
>
> **Q12 nasceu nesta sessão, e nasceu certa:** feita antes de escrever o caso de
> uso, sobre consequência observável, conferida rodando `lint-imports` na hora.
> Foi **errada duas vezes** — a reformulação que a regra permite já foi gasta,
> então ela entra na fila em vez de ser fechada por explicação do agente. As duas
> execuções estão no CARD-009 e no ADR-0036.
>
> **Quinta sessão seguida com o item vermelho.** A proposta de postmortem sobre a
> **regra** (não sobre a sessão) foi feita na abertura do CARD-009 e também ficou
> sem resposta. Reescrever uma regra da constituição é decisão do desenvolvedor,
> então o postmortem não foi escrito — fica como a pendência de topo desta fila.

> **CARD-010 (2026-08-23): a fila FOI reapresentada na abertura** — Q2, Q7 e Q12,
> com o motivo de cada uma tocar aquele card (a primeira sessão em que `api` e
> `worker` de fato se falam; seis dublês de porta trocados por
> `dependency_overrides`; duas dependências novas entrando nas listas
> `forbidden`). A **proposta de postmortem sobre a regra** foi reapresentada
> junto, como pendência de topo. **Nenhuma das quatro foi respondida nem
> dispensada:** o desenvolvedor respondeu as quatro decisões de escopo (forma do
> `Result`, esquema de `id` do SSE, idempotência, token de dev) e pediu para
> seguir. Silêncio não é dispensa (LEARNING-0004).
>
> Pela sexta vez, as perguntas se demonstraram sozinhas — e desta vez **duas
> vezes na mesma sessão para a Q7**: o `mypy` reprovou `FakeTurnRepository` no
> instante em que `TurnRepository` ganhou `get_by_idempotency_key`, e
> `FakeTurnEvents` no instante em que `TurnEvents` ganhou `subscribe`, com o
> `pytest` verde nas duas. A **Q12** ganhou o par completo: `sse_starlette` em
> `application` com o módulo na lista → `BROKEN`; `starlette` na mesma posição
> com o módulo **fora** da lista → `4 kept, 0 broken` — e essa segunda metade
> revelou uma lacuna real, `starlette` faltando nas listas desde o CARD-001.
>
> **Q13 nasceu nesta sessão, e nasceu certa:** feita antes de escrever a porta,
> sobre consequência observável, num ponto em que errar custa um trecho de áudio
> perdido de forma intermitente. Também sem resposta. A decisão foi tomada
> (porta como context manager) e há dois testes que a sustentam — um com dublê e
> um contra Redis real —, mas **teste não fecha item de aprendizado**.
>
> **Sexta sessão seguida com o item vermelho.** A pendência de topo desta fila
> continua sendo a mesma: decidir se a **regra** muda.

> **CARD-011 (2026-08-24): a fila FOI reapresentada na abertura** — Q7 e Q1,
> com o motivo honesto de cada uma tocar este card. A fila tem 10 abertas e é
> **toda de backend**; este card é de front-end, e o agente disse isso em vez de
> forçar as outras oito para cumprir tabela. **Q7** entrou pelo paralelo (este
> card decide se o TypeScript roda com `strict`, e a pergunta gêmea é *"o que
> quebra, e quando, se o backend renomear um campo?"*); **Q1** entrou pela
> fronteira de empacotamento (o Metro e os symlinks do pnpm). A **proposta de
> postmortem sobre a regra** foi reapresentada como pendência de topo, com os
> três caminhos possíveis explicitados (manter e responder / reescrever /
> manter e aceitar o vermelho como dívida). **Nenhuma das três foi respondida
> nem dispensada:** o desenvolvedor respondeu as quatro decisões de escopo
> (Biome, `expo-router` entra, teste adiado, tokens agora) e a sessão seguiu.
>
> Pela sétima vez, as perguntas se demonstraram sozinhas. **Q7:** renomear
> `TurnResponse` no schema gerado ⇒ `error TS2339: Property 'TurnResponse' does
> not exist`, revertido ⇒ verde — o par completo que torna verdadeira a promessa
> do ADR-0008, que até esta sessão era **falsa** (ninguém compilava cliente
> nenhum contra os tipos). **Q1:** o primeiro bundle saiu
> `node_modules/.pnpm/expo-router@57.0.15_…/entry.js`, provando que o Metro
> resolve através da store do pnpm — a mesma classe de pergunta ("o que o import
> resolve depende de como o pacote foi instalado"), agora do outro lado do
> monorepo.
>
> **Q14 nasceu nesta sessão, e nasceu certa:** feita antes de escrever o spike,
> sobre consequência observável, num ponto em que errar custaria uma dependência
> desnecessária no app (`react-native-sse`) ou um card inteiro perdido no 012.
> Conferida rodando na hora: **(a) chega em pedaços** — 5 leituras, timestamps
> crescentes, `chunk 0` em 1,65 s. Também sem resposta.
>
> **Sétima sessão seguida com o item vermelho.** A pendência de topo desta fila
> continua sendo exatamente a mesma desde o CARD-009: decidir se a **regra**
> muda. Ela é a única linha desta fila que não depende de mais uma sessão de
> trabalho para ser resolvida — depende de uma decisão de uma frase.

## Fechadas

| # | Pergunta | Fechada em | Como |
|---|---|---|---|
| Q3 | Contrato de **dependência** vs. contrato de **direção** no import-linter: em que cenário só o segundo pega a violação? | 2026-08-19 (CARD-006) | Perguntada **antes** de escrever as listas `forbidden` dos módulos de STT. Primeira resposta parcialmente errada ("A quebra o forbidden"): a violação A — `from faster_whisper import ...` em `application`, com o módulo fora da lista — passou **verde**, `4 kept, 0 broken`. Demonstrado o par completo (mesma linha, com o módulo na lista → `BROKEN`) e **reformulado** uma vez. Respondida corretamente: apagando os contratos `forbidden`, só o `layers` quebra, e **nenhuma lista o torna redundante** — `layers` opera sobre o grafo interno sem lista, `forbidden` é o único que enxerga biblioteca de terceiros |
| Q10 | `jiter.from_json(buf, partial_mode=True)` sobre `b'{"spoken_reply": "Hi there, how ar'`: o que devolve, e por que isso mataria a cascata? | 2026-08-21 (CARD-007) | Perguntada **antes** de escrever o parser incremental. Primeira resposta **errada** (`{'spoken_reply': 'Hi there, how ar'}` — que é o que o `trailing-strings` devolve, não o `True`). Demonstrada com as três chamadas no terminal: `trailing-strings` → a string incompleta vem; `True` → `{}`; sem `partial_mode` → `ValueError: EOF while parsing a string`. Explicado o porquê (`True` só entrega valores **completos**, e uma string sem a aspa de fechamento não é um) e a consequência: a fala só apareceria quando estivesse inteira, que é esperar o objeto fechar — o card falhando em silêncio. **Reformulada uma vez** (quais trechos podem ir ao TTS com `"Hi there. How are yo"`) e **respondida corretamente**: só `"Hi there."`, porque só o que tem delimitador **e texto depois** está provadamente fechado |
| Q8 | Que falha o `lint-imports` **não** pega com a lista `forbidden` desatualizada? | 2026-08-18 (CARD-005) | Perguntada **no ponto da decisão**, antes de adicionar `sqlalchemy`. Primeira resposta errada ("o contrato de layers pega"); demonstrada com a violação injetada (`4 kept, 0 broken` com a violação dentro → `BROKEN` depois de atualizar a lista); **reformulada** e respondida corretamente: gate verde significa "nenhuma violação **entre as que eu listei**" |
