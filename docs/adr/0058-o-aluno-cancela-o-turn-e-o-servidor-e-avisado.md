# ADR-0058 — O aluno cancela o turn, e o servidor é avisado

- **Status:** aceito
- **Data:** 2026-09-09
- **Critério de obrigatoriedade** (`docs/adr/README.md`): **2 — define ou altera
  uma fronteira** (endpoint novo em `/v1` e um desfecho novo no ciclo de vida do
  `Turn`, que é estado persistido).

## Contexto

Segundo apontamento do primeiro uso real: *"ao errar a gravação e tentar
recomeçar, o app continua falando"*. O comportamento desejado é o óbvio — o
professor cala a boca para ouvir o aluno.

**A investigação de 2026-09-09 encontrou algo que o briefing não previa: a peça
do cliente já está ligada.** `TelaConversa.tsx:86` já chama `turno.limpar()`
antes de `gravacao.iniciar()`, e `limpar()` já aborta a conexão viva
(`abortador.current?.abort()`) e já chama `fila.limpar()`, que percorre os
players e chama `remove()` em cada um. Ou seja: **o ponto 2 do briefing não é
uma feature faltando, é um bug** — e a hipótese principal é que
`useFilaDePlayback.ts` chama `player.remove()` **sem `pause()` antes**, deixando
o áudio já em buffer terminar de sair. Isso é trabalho de cliente, e é o
CARD-042; **não precisa de ADR** (correção sem mudança de design → `learnings/`).

O que precisa de decisão é o outro lado. Com o cliente calado, o servidor
continua trabalhando: STT já rodou, o professor está gerando, o TTS está
sintetizando e o S3 recebendo trechos que ninguém vai ouvir. A pergunta que o
briefing mandou responder primeiro — *quanto custa um turn abandonado?* — tem
número: **US$ 0,002678 por turn**, medido no CARD-014. São ~370 abandonos por
dólar. **Em dinheiro, isto é ruído.**

**A decisão de produto tomada em 2026-09-09 foi cancelar no servidor assim
mesmo**, sabendo do número. O argumento que prevaleceu não é o custo: é que o
ADR-0003, item 2, afirma que a entidade `Turn` foi modelada para acomodar
cancelamento **em preparação para o V2**, e uma afirmação dessas ou é exercida
ou apodrece. O V2 (barge-in real) precisa cancelar em voo por desenho, não por
economia; construir o caminho agora, com um gatilho simples e um turn por vez, é
pagar barato por uma fronteira que o realtime vai cobrar cara.

## Decisão

**O cliente avisa o servidor quando o aluno abandona um turn, e "cancelado" é um
desfecho de primeira classe do `Turn`.**

1. **`POST /v1/turns/{id}/cancel`**, e não `DELETE`. Nada é apagado: o turn
   existe, foi cobrado no que já consumiu, e continua no histórico. `DELETE`
   prometeria remoção e a decisão de 2026-08-27 sobre "Descartar" (CARD-032) já
   fixou que o produto **não apaga nada**.
2. **Idempotente por natureza, não por chave.** Cancelar um turn já cancelado é
   `200`, não `409` — o cliente pode reenviar sem pensar, e um retry de rede não
   é um caso especial. Cancelar um turn já `completed` também é `200` e **não
   faz nada**: a corrida "terminou enquanto o dedo ia ao botão" é o caso comum,
   não o excepcional.
3. **Cancelamento é cooperativo, e o worker é quem coopera.** A API marca a
   intenção; o worker verifica entre as etapas da cascata (ADR-0037: a cascata é
   uma fila interna com um consumidor só, e ela tem pontos naturais de
   verificação entre sentenças). Não há `kill` de task do `arq` — matar a
   corrotina no meio deixaria trecho meio escrito no S3 e `UsageEvent` sem
   fechar. **O turn cancelado para no próximo ponto de verificação, não no
   instante do clique.**
4. **O que já foi gerado permanece.** Trechos já no S3 seguem a retenção normal
   do ADR-0024, e o `UsageEvent` registra o que foi de fato consumido até o
   corte — porque o custo foi real, e o ADR-0051 congela o custo na escrita.
   Turn cancelado que reportasse custo zero mentiria no dashboard de custo.
5. **O cliente não espera pela resposta para calar.** Silenciar é local e
   imediato (CARD-042); o `cancel` é uma notificação disparada em paralelo, e
   falhar nela **não** é erro visível ao aluno — no pior caso o servidor termina
   um turn que ninguém ouve, que é exatamente o estado de hoje.

## Alternativas consideradas

### Alternativa A — o cliente só ignora; o servidor termina

O caminho de menor esforço, e o que o próprio briefing indicava como
provavelmente suficiente: um card só de cliente, sem endpoint, sem estado novo,
sem migração. O custo de manter é US$ 0,0027 por abandono.

Rejeitada **por decisão do desenvolvedor em 2026-09-09**, ciente do número. O
motivo registrado não é econômico: é que o cancelamento em voo é infraestrutura
do V2 (ADR-0003), e o V1 é onde ela sai barata — um consumidor, um turn de cada
vez, sem contenção. Fica registrado que **se o CARD-043 se mostrar maior do que
uma sessão, esta alternativa é o recuo**, e ela é aceitável: o produto não
degrada, só gasta.

### Alternativa B — impedir regravar enquanto o professor fala

Bloquear o botão. Rejeitada sem hesitação: é precisamente o que incomodou no uso
real, agora oficializado como regra. Piorar a experiência para simplificar o
servidor inverte a ordem das prioridades do projeto.

### Alternativa C — cancelamento por timeout implícito, sem endpoint

Deixar o worker perceber que o SSE caiu e desistir sozinho. Rejeitada porque
confunde duas coisas diferentes: o cliente **cai** (túnel, background do iOS,
tela travada — casos em que o turn deve continuar e ser recuperado na retomada,
que é a razão de existir do ADR-0041) e o aluno **desiste**. Só o segundo é
cancelamento, e só o cliente sabe qual dos dois aconteceu. Adivinhar pela
conexão transformaria toda ida ao background numa perda de turn.

## Consequências

- **Positivas:** o caminho de cancelamento existe e é exercitado antes de o V2
  depender dele. O `Turn` deixa de ter um estado que só a documentação afirma.
  Trabalho e dinheiro deixam de ser gastos com resposta que ninguém ouve, e o
  `UsageEvent` passa a distinguir turn consumido de turn abandonado — que é
  informação de produto (uma taxa alta de abandono é sinal de resposta lenta ou
  de STT errando).
- **Negativas:** um endpoint novo é superfície nova — precisa de limite, de
  autenticação e de testes de rota; a decisão de "quem pode cancelar o quê"
  chega junto. O cancelamento cooperativo **não é instantâneo**, e a diferença
  entre "cliente calou" e "servidor parou" é uma janela que vai aparecer em
  log e confundir depuração se não for nomeada. Um estado a mais no `Turn`
  toca a derivação de etapa (ADR-0028), a retomada por SSE (ADR-0041) e a
  varredura de travados (CARD-025) — três lugares que passam a ter um caso novo.
- **Equivalente mental .NET:** é um `CancellationToken` cujo `Cancel()` vem de
  outro processo. O `IsCancellationRequested` verificado entre etapas é
  exatamente o item 3 — e a lição é a mesma que em .NET: cancelamento
  cooperativo depende de alguém checar, e o ponto de checagem é decisão de
  desenho, não detalhe.
