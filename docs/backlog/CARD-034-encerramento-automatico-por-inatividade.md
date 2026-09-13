# CARD-034 — Encerramento automático por inatividade: a sessão que ninguém fechou deixa de ficar aberta para sempre

- **ID:** CARD-034
- **Épico:** Fase 3 — Domínio pedagógico
- **Plataforma:** backend · **Esforço:** P · **Status:** concluído (2026-09-13)
- **Dependências:** CARD-031 (**o `end` explícito vem primeiro**), CARD-025 (o irmão desta varredura); ADR-0005

## Contexto

Decidido em 2026-08-27, ao fechar o RNF5 do CARD-031: **existe** encerramento
automático, e o critério é **inatividade** — sem turn novo há N minutos.

O CARD-031 entrega o encerramento **explícito** (o aluno toca "Encerrar"). Este
card cobre o caso muito mais comum: o aluno fecha o app e some.

## Problema

**A maioria das sessões nunca vai ser encerrada por ninguém.**

"Encerrar" é um botão que exige que o aluno se lembre dele. Sem este card, o
histórico do CARD-030 mostra uma pilha de sessões "em andamento" que acabaram
há semanas, e o resumo pós-sessão do artboard 09 — que é o momento pedagógico do
produto — simplesmente nunca acontece para quem não tocou no botão.

Pior: `ended_at` nulo passa a significar duas coisas diferentes ("está falando
agora" e "sumiu em julho"), e um campo que significa duas coisas não significa
nenhuma.

## Requisitos funcionais

- **RF1** — Um job periódico encerra sessões sem turn novo há mais que um prazo
  **configurável**, usando o mesmo `Session.end()` do domínio — nunca um
  `UPDATE` direto.
- **RF2** — A inatividade é medida a partir do **último turn** da sessão; sessão
  sem turn nenhum conta a partir de `started_at`.
- **RF3** — Uma sessão com turn **ainda em processamento** não é encerrada pela
  varredura, mesmo que o último turn seja antigo — o aluno pode estar esperando
  uma resposta travada, e o CARD-025 é quem cuida daquilo.
- **RF4** — O encerramento automático é **indistinguível** do explícito para
  quem lê: o histórico não ganha um "encerrada automaticamente". Se um dia
  precisar distinguir, é campo novo com motivo escrito, não inferência por
  horário.
- **RF5** — O prazo é folgado o bastante para o aluno **pensar entre falas**. É
  a decisão central do card e tem de sair de um número, não de gosto: um aluno
  ouvindo 17 s de resposta, pensando e formulando uma frase em inglês leva
  minutos, não segundos.

## Requisitos não funcionais

- **RNF1 — Roda no worker, não na API.** Mesma decisão do CARD-025, pelo mesmo
  motivo: é `cron_jobs` do `arq`, e o card deve escrever o que acontece com mais
  de uma réplica (hoje `MAX_JOBS = 1`, mas o comportamento com duas não pode ser
  surpresa).
- **RNF2 — A varredura não carrega o mundo.** Encerrar 500 sessões velhas não
  pode significar 500 round-trips nem uma transação gigante. Lote com limite, e
  o limite é parâmetro.
- **RNF3 — Idempotente por construção.** Uma sessão já encerrada não é candidata
  na consulta seguinte; e se duas execuções se sobrepuserem, a segunda não pode
  levantar `InvalidStateTransitionError` em massa e derrubar o job.
- **RNF4 — Relógio testável.** O prazo é testado com relógio controlado, como o
  CARD-025 exige — nunca com `sleep`.
- **RNF5 — Não conflita com a cota.** A cota vira por **dia-calendário em fuso
  fixo** (CARD-015); a sessão fecha por **inatividade**. São duas janelas
  diferentes de propósito, e o card não deve alinhá-las por conveniência.

## Escopo

- **In:** o `cron_job`; a consulta de sessões candidatas; o encerramento em
  lote via domínio; o prazo configurável com a conta escrita; testes com relógio
  controlado.
- **Out:** notificar o aluno de que a sessão fechou (é push, cortado pela visão
  §F); o resumo pós-sessão sendo **entregue** ao aluno depois do fato (ele o vê
  no histórico, CARD-030); distinguir encerramento automático de explícito
  (RF4).

## Critérios de aceite

- **Dado** uma sessão cujo último turn foi há mais que o prazo, **quando** a
  varredura roda, **então** ela fica encerrada com `ended_at` preenchido.
- **Dado** uma sessão dentro do prazo, **então** a varredura não a toca.
- **Dado** uma sessão antiga **com um turn `processing`**, **então** a varredura
  não a encerra.
- **Dado** uma sessão aberta sem nenhum turn há mais que o prazo, **então** ela
  é encerrada.
- **Dado** 200 sessões candidatas e um lote de 50, **então** a execução encerra
  50 e a seguinte encerra as próximas — sem erro e sem pular nenhuma.
- **Dado** uma sessão já encerrada, **então** ela nunca reaparece como
  candidata.

## Riscos

- **Prazo curto encerra o aluno que foi ao banheiro.** Ele volta, grava, e o
  turn é **recusado** pelo RF3 do CARD-031 — a fala se perde. É o modo de falha
  mais irritante possível e o único jeito de evitá-lo é o prazo do RF5 ser
  generoso. Errar para o lado longo custa uma sessão aberta por mais tempo;
  errar para o curto custa a fala do aluno.
- **Interação com o CARD-027.** A fila offline sobe falas antigas. Se a
  varredura encerrar a sessão enquanto uma fala está na fila do aparelho, ela é
  recusada na subida. Isso é **coerente** com a decisão do CARD-031, mas precisa
  estar escrito nos dois cards para ninguém tratar como bug.
- **Dois `cron_jobs` no mesmo worker** (este e o CARD-025) disputando o mesmo
  processo com `MAX_JOBS = 1`: eles competem com o processamento de turn. Prazos
  longos e lotes pequenos são o que impede a varredura de atrasar um aluno vivo.

## Objetivo de aprendizado

`cron_jobs` do `arq` com mais de um job registrado — como eles se intercalam com
o consumo normal da fila num worker de concorrência 1, que é o oposto do modelo
mental de um `IHostedService` rodando em paralelo ao resto do host em .NET.

## Execução (2026-09-13, loop autônomo)

**RF1 — e a divergência com a letra do requisito, resolvida e escrita.** O RF1
pede "o mesmo `Session.end()` do domínio — nunca um `UPDATE` direto". O que
este card **não** faz é escrever SQL ad-hoc; mas o encerramento passa por
`SessionRepository.try_end`, não por `Session.end()`. A razão está no docstring
do próprio `Session.end()`, escrito no CARD-031: *"a mutação de verdade não
passa por aqui em produção"* — dois processos que chamam `end()` em memória não
veem a escrita um do outro antes de comitar, e usar `end()` aqui reabriria a
corrida que aquele card fechou com um `UPDATE ... COALESCE` atômico. `try_end`
**é** a regra do domínio, expressa atomicamente.

O ganho aparece de graça no **RNF3**: `try_end` é idempotente por construção —
sessão já encerrada devolve o `ended_at` que já tinha, sem levantar. Não há
`InvalidStateTransitionError` em massa a capturar, porque não há exceção
nenhuma. É estritamente mais robusto que o padrão do CARD-025, que precisa do
`try/except` por item.

**RF2** — o marco de atividade é `coalesce(max(turn.created_at), started_at)`.
Sem o `coalesce`, a sessão sem turn teria marco `NULL`, e `NULL < :before` é
`NULL` e não `true`: ela nunca seria candidata, em silêncio. É o mesmo buraco
que o `list_stale` do CARD-025 já tinha nomeado para o turn `queued`, e há
teste contra Postgres real cobrindo exatamente isso.

**RF3** — a exclusão da sessão com turn `queued`/`processing` acontece no
`HAVING`, com `count(...) FILTER (WHERE ...)` do Postgres — um agregado
condicional, não um segundo round-trip.

**RF4** — nada distingue o encerramento automático do explícito: os dois
escrevem só `ended_at`, pelo mesmo caminho. Nenhum campo de motivo foi criado.

**RF5 — o número, com a conta.** `inactive_session_after = 30 min`. O ciclo é:
o aluno ouve ~17 s de resposta, pensa, formula uma frase em inglês — minutos,
não segundos —, e sobre isso corre a vida real (campainha, trabalho, banheiro).
**A assimetria do erro é o que fixa o valor:** errar para o lado longo custa uma
sessão aparecendo como "em andamento" por mais tempo; errar para o curto custa
**a fala do aluno** (ele volta, grava, e o turn é recusado com `session-ended`).
Gatilho para revisar: medir o percentil 99 do intervalo entre turns com o
`occurred_at` do `UsageEvent`.

**RNF1** — `cron_job` no worker, a cada 5 min, no **segundo 30**. A cada 5 min
porque o prazo é de 30: detectar 60 s antes não muda nada e cada rodada disputa
o `MAX_JOBS = 1` com quem está falando agora. No segundo 30 para não cair junto
com a varredura de turns (segundo 0) — duas varreduras no mesmo instante são o
dobro de espera para o aluno vivo. A coordenação entre réplicas é a mesma do
CARD-025 (`job_id` determinístico do `arq`), e aqui ela importa menos porque
`try_end` já é idempotente.

**RNF2** — lote de 50, parâmetro; um commit por sessão, não um por rodada.

**RNF4** — relógio controlado em todos os 8 testes de regra; nenhum `sleep`.

**RNF5** — as duas janelas seguem diferentes de propósito: a cota vira por
dia-calendário em fuso fixo (ADR-0063), a sessão fecha por inatividade. Nada
neste card as alinha.

**Mudança estrutural de passagem:** `RowNotFoundError` **mudou de camada** — do
adapter para a porta. A razão é a que o `LlmError` já registra no projeto:
*onde o erro mora é consequência de quem precisa capturá-lo*. Esta varredura o
captura por item (uma sessão apagada entre a listagem e a escrita não pode
derrubar o lote), e `application` não pode importar `adapters` — o
`lint-imports` pegaria. O adapter continua levantando-a; mudou de onde ele a
importa.

**A corrida residual, registrada porque é aceita** (e o Risco nº 2 do card pede
que esteja escrita nos dois lados): entre a listagem e o `try_end`, o aluno
pode falar; a sessão fecha e o turn seguinte é recusado com `session-ended`. A
defesa escolhida **não** é lock — é o prazo generoso do RF5. A janela é de
milissegundos dentro de uma rodada contra 30 minutos de silêncio, e o desfecho,
quando acontece, é um 409 que o app sabe explicar (CARD-031, RF3). O mesmo vale
para a fila offline do CARD-027.

**Testes:** `tests/application/test_sweep_inactive_sessions.py` (8, relógio
controlado — inclusive o lote em três rodadas e a sessão apagada no meio),
`tests/adapters/test_persistence.py` (5 novos contra Postgres real — o
`coalesce`, o `FILTER` do RF3, a ordem e o lote).

**Nenhum ADR novo:** nenhum critério de `docs/adr/README.md` se aplica. Não há
dependência nova, nenhuma fronteira de contrato muda (o job não tem API), não
afeta custo recorrente nem segurança, é trivialmente reversível (desligar o
`cron`), e não contraria convenção — ao contrário, aplica as do CARD-025 e do
CARD-031. A única decisão com peso (o prazo do RF5) é configuração com a conta
escrita em `config.py`, não arquitetura.

**Regra do explicador:** nenhuma pergunta de previsão coube — a única decisão
de produto (o prazo) tinha uma direção claramente segura pela assimetria do
erro, e foi tomada com a conta registrada em vez de perguntada.
