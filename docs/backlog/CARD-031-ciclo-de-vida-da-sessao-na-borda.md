# CARD-031 — O ciclo de vida da sessão chega à borda, e a fala atrasada deixa de ser 409 mudo

- **ID:** CARD-031
- **Épico:** Fase 3 — Domínio pedagógico (backend dos artboards 09 e 14)
- **Plataforma:** backend · **Esforço:** M · **Status:** backlog
- **Dependências:** CARD-010 (concluído), CARD-013 (concluído); ADR-0017, ADR-0039, ADR-0040

## Contexto

Backend de duas telas: o **"Encerrar"** do artboard 09 (resumo pós-sessão) e o
**offline** do artboard 14, que o [CARD-027](CARD-027-telas-de-excecao-do-app.md)
implementa no cliente.

O domínio já está pronto — e é justamente por isso que o buraco é visível.

## Problema

**1. `Session.end()` existe e ninguém o chama.**

`domain/session.py:71` implementa o encerramento, com a transição protegida.
`api/routes/sessions.py` tem **só** `POST /sessions`. Não há
`POST /v1/sessions/{id}/end`. A regra que o CARD-005 escreveu está inalcançável
pelo produto: hoje **nenhuma sessão jamais é encerrada**, o que significa que
`ended_at` é sempre nulo e `is_active` é sempre verdadeiro.

**2. A fala que chega atrasada bate num 409 indiferenciado — e ela não é um bug
de quem chamou.**

`Session.start_turn()` recusa sessão encerrada com `InvalidStateTransitionError`
(`domain/session.py:59`), que é `DomainError`, que o handler traduz em **409
`invalid-state`** (`api/errors.py:183`). O docstring do próprio método diz por
que a invariante existe: *"uma fala gravada às 21h pode chegar ao servidor às
23h, depois de a sessão ter sido encerrada"*.

Mas o `StartTurnHandler` declara `Result[TurnAccepted, SessionNotFound]` — não
há variante para "sessão encerrada". A pergunta do ADR-0039 é *"quem chamou tem
um bug?"*, e **a fila offline não tem**: ela fez exatamente o que foi desenhada
para fazer. Hoje o app recebe um 409 genérico e não consegue distinguir "sua
sessão de ontem fechou" de qualquer outra violação de estado — os dois têm a
mesma URN.

**3. O resumo pós-sessão não tem de onde sair.** O artboard 09 mostra
*"Você falou inglês por 8 minutos hoje · 7 turnos · 5 correções"* no momento do
encerramento. Nenhum endpoint devolve isso.

## Requisitos funcionais

- **RF1** — `POST /v1/sessions/{id}/end` encerra a sessão e devolve o **resumo**:
  duração falada, nº de turns, nº de correções por tipo.
- **RF2** — Encerrar é **idempotente do ponto de vista do cliente**: encerrar
  duas vezes não é erro do app, e a resposta da segunda diz a mesma coisa da
  primeira. (O domínio levanta na segunda — quem traduz isso é a borda, e essa
  tradução é o desenho deste card.)
- **RF3** — Um turn que chega para uma sessão encerrada tem **desfecho próprio e
  distinguível**, com URN própria em Problem Details — não o `invalid-state`
  genérico. O app precisa saber dizer *"sua fala de ontem não entrou porque a
  sessão fechou"*, e o que oferecer no lugar.
- **RF4 — DECIDIDO (2026-08-27): a fala é recusada, e o app avisa.** Nada de
  abrir sessão nova pelo servidor nem de relaxar a invariante. A sessão continua
  sendo um recipiente de fronteira firme, e o resumo pós-sessão nunca muda
  depois de mostrado. O que o aluno faz a seguir é decisão dele — gravar de novo
  numa sessão nova é um turn novo, com `Idempotency-Key` nova.
- **RF5** — Uma sessão sem turn nenhum pode ser encerrada (o aluno abriu e
  desistiu), e o resumo vem zerado.
- **RF6 — DECIDIDO (2026-08-27): encerrar não espera, e o turn em voo conclui
  normalmente.** A recusa do RF3 vale para turn **novo**, nunca para turn já
  aceito: um turn que já está na fila termina dentro da sessão que o recebeu, e
  seus trechos continuam sendo entregues pelo SSE. A consequência aceita é que
  **o resumo devolvido pelo `end` pode ficar defasado por segundos** — o app
  reconsulta se quiser o número final, e o card escreve isso no schema em vez de
  fingir precisão.

## Requisitos não funcionais

- **RNF1 — O desfecho esperado é `Err`, não exceção** (ADR-0039). Acrescentar a
  variante muda o `E` do `Result` do `StartTurnHandler`, e o `assert_never` da
  rota **para de compilar** até o caso novo ser tratado. Isso é o mecanismo
  funcionando.
- **RNF2 — A invariante de domínio não sai do domínio.** `Session.start_turn`
  continua recusando; o que muda é **quem pergunta antes** e como a borda
  traduz. Substituir a exceção por um `if` no caso de uso, sem a guarda do
  agregado, é regredir o ADR-0017.
- **RNF3 — URN nova é adição, não mudança** (ADR-0008): cliente antigo que não
  conheça a URN nova continua tratando o 409 pelo status.
- **RNF4 — Sem corrida no encerramento.** Dois `end` concorrentes, ou um `end`
  concorrente com um `POST` de turn, não podem produzir sessão encerrada **com**
  turn aceito depois. É a mesma classe de teste que o CARD-015 exige para cota.
- **RNF5 — DECIDIDO (2026-08-27): existe encerramento automático por
  inatividade**, e ele é **[CARD-034](CARD-034-encerramento-automatico-por-inatividade.md)**
  — job periódico do worker, irmão da varredura do CARD-025, nunca um `if` na
  leitura. Este card entrega o encerramento **explícito**; o automático usa o
  mesmo `Session.end()` e por isso vem depois, não junto.

## Escopo

- **In:** o endpoint de encerramento com resumo; o desfecho tipado de sessão
  encerrada no POST de turn, com URN própria; o teste de corrida; o
  comportamento do RF6 provado (turn em voo conclui depois do `end`).
- **Out:** a tela de resumo (CARD-016) e a tela de offline (CARD-027); o
  encerramento **automático**, que é o CARD-034.

## Critérios de aceite

- **Dado** uma sessão com 7 turns e 5 correções, **quando** encerro, **então**
  recebo o resumo com os três números e `ended_at` gravado.
- **Dado** uma sessão já encerrada, **quando** encerro de novo, **então** o app
  recebe o que foi decidido no RF2 — e o teste afirma qual é.
- **Dado** uma sessão encerrada, **quando** chega um POST de turn com áudio,
  **então** a resposta é Problem Details com a **URN de sessão encerrada**,
  distinta de `invalid-state`, e nenhum turn é criado.
- **Dado** dois `end` concorrentes, **então** um vence e o outro recebe o
  desfecho do RF2 — nunca dois `ended_at` diferentes.
- **Dado** um turn `processing`, **quando** a sessão é encerrada, **então** o
  turn conclui normalmente, seus trechos continuam chegando pelo SSE, e um POST
  de turn **novo** na mesma sessão é recusado.
- **Dado** o `Result` do `StartTurnHandler` com a variante nova, **então** o
  `mypy` reprova a rota até ela tratar o caso.

## Riscos

- **O RF6 cria uma janela em que a sessão está encerrada e ainda muda.** Entre
  o `end` e a conclusão do turn em voo, as contagens da sessão crescem depois de
  `ended_at`. Nada quebra, mas qualquer código que assuma *"sessão encerrada é
  imutável"* vai estar errado — inclusive um futuro cache do CARD-030. Escreva
  a suposição em vez de deixá-la implícita.
- **Nunca ter encerrado sessão nenhuma esconde bugs.** O caminho de encerramento
  nunca rodou em nenhum ambiente. Espere encontrar coisas.

## Objetivo de aprendizado

Como uma união fechada (`Result` + `match` + `assert_never`) força exaustividade
no `mypy` — e por que isso é mais forte que o `switch` exaustivo do C#, que só
avisa em tempo de execução quando o `default` cai. Junto: a diferença entre
invariante do agregado (exceção) e desfecho esperado (`Err`) aplicada ao **mesmo
fato** visto de dois lugares — que é a pergunta central do ADR-0017 × ADR-0039.
