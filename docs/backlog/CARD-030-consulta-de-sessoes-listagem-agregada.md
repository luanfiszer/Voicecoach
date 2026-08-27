# CARD-030 — Consulta de sessões: a listagem agregada e o áudio que já expirou

- **ID:** CARD-030
- **Épico:** Fase 3 — Domínio pedagógico (backend do artboard 10)
- **Plataforma:** backend · **Esforço:** M · **Status:** backlog
- **Dependências:** CARD-013 (concluído), CARD-017; ADR-0008, ADR-0024, ADR-0051

## Contexto

Backend do [CARD-029](CARD-029-historico-de-sessoes-no-app.md) (artboard 10).
A tela existe desenhada desde 2026-08-17 e o servidor não sabe responder a
pergunta dela: **"quais foram minhas sessões?"**.

`api/routes/sessions.py` tem **só** `POST`. O `SessionRepository` tem
`add`/`get`/`update` — nenhuma listagem. Não é um endpoint faltando: é uma
capacidade de consulta que nunca existiu.

## Problema

Além da listagem, a tela revela uma regra que o backend **tem** e nunca expôs:

> *"Áudio expirado — transcrição e correções permanecem"*

O ADR-0024 e o CARD-017 decidiram retenção **assimétrica**, e os números em
`config.py:238-240` são fortes: `retention_reply_chunk` = **1 dia**,
`retention_reply_full` = 90 dias, `retention_input` = 7 dias. Ou seja, os
trechos de áudio da conversa de **ontem** já expiraram — o artboard mostra o
aviso só na terceira linha, mas na prática ele aparece quase sempre.

Se o cliente inferir isso por data, ele erra no dia em que a política mudar; e
ela é configuração, não constante.

## Requisitos funcionais

- **RF1** — `GET /v1/sessions` devolve as sessões do aluno, **mais recente
  primeiro**, com: `id`, `started_at`, `ended_at`, duração falada, nº de turns e
  nº de correções.
- **RF2** — A janela é parâmetro do contrato, com default de **30 dias** (a tela
  promete *"sessões anteriores a 30 dias vivem no app web"*). O que ficou fora
  da janela não é erro: é ausência.
- **RF3** — Cada sessão informa se a **mídia de resposta ainda está
  disponível**, derivado da política de retenção vigente — nunca calculado pelo
  cliente a partir da data.
- **RF4** — Sessão **sem nenhum turn** aparece na listagem (o aluno abriu e não
  falou), com contagens zeradas — zero é dado, não ausência, exatamente como o
  ADR-0051 decidiu para custo.
- **RF5** — Aluno sem sessão nenhuma recebe lista vazia com `200`, nunca `404`.
- **RF6** — A duração falada da sessão é a **soma dos `audio_duration`** dos
  seus turns, e ela é a mesma unidade que a tela de conversa mostra ("6 min") e
  que o CARD-015 pode usar como cota. Uma definição, um lugar.

## Requisitos não funcionais

- **RNF1 — O número de queries não cresce com o número de sessões.** As
  agregações são feitas **no banco** (`func.count`/`func.sum`), como
  `totals_for_student` do CARD-014 já faz. O `lazy="raise_on_sql"` protege
  contra tocar coleção; **não** protege contra um laço que chama o repositório
  por linha. Provado com log de SQL, do jeito que o CARD-013 provou o
  `selectinload`.
- **RNF2 — Índice antes da consulta.** A listagem filtra por `student_id` e
  ordena por `started_at`: igualdade antes de faixa, a mesma ordem que o índice
  de `usage_events` já usa. Sem ele, a tela mais aberta do app faz seq scan.
- **RNF3 — Contrato aditivo** (ADR-0008): campo novo é opcional e nenhum enum
  existente ganha valor. Um cliente antigo continua lendo a listagem.
- **RNF4 — Refinamento de cache e limite** (template, §"Refinamento
  obrigatório"): esta é uma leitura repetida a cada abertura da aba. **Ou** se
  define TTL e gatilho de invalidação (um turn novo invalida a sessão do dia),
  **ou** se registra por escrito que não há cache e por quê. Ficar em silêncio
  não é opção.
- **RNF5 — Custo de leitura não conta como consumo.** A listagem é leitura: não
  gasta cota, não incrementa budget, e continua respondendo com a cota estourada
  (a regra "quota bloqueia escrita, não leitura", já fixada no CARD-015).
- **RNF6 — Sem N+1 de URL assinada.** A listagem **não** assina URL de mídia:
  assinar é HMAC local (ADR-0045), mas 30 sessões × N trechos é trabalho inútil
  para uma tela que não toca áudio. URL assinada é da tela de detalhe, que é web.

## Escopo

- **In:** o endpoint, a query agregada no repositório, o índice, a derivação de
  disponibilidade de mídia, o schema de resposta e os testes (incluindo o de
  contagem de queries).
- **Out:** abrir uma sessão e reproduzir a conversa inteira (é a análise
  completa, e é web — Fase 5); busca e filtro; paginação por cursor (a janela de
  30 dias é o corte, e se um dia não bastar, é card próprio); a tela
  (CARD-029).

## Critérios de aceite

- **Dado** um aluno com 3 sessões, **quando** chamo `GET /v1/sessions`,
  **então** recebo as 3 ordenadas da mais recente para a mais antiga, com as
  contagens corretas.
- **Dado** 30 sessões na janela, **então** o número de queries executadas é o
  mesmo que para 3 — provado no log de SQL.
- **Dado** uma sessão cujos trechos passaram da retenção, **então** o campo de
  disponibilidade de mídia diz que expirou, e transcrição e correções continuam
  vindo íntegras.
- **Dado** uma sessão aberta sem nenhum turn, **então** ela aparece com
  contagens em zero.
- **Dado** um aluno com a cota do dia estourada, **então** a listagem responde
  `200` normalmente.

## Riscos

- **A agregação de correções convida ao N+1**, porque `Correction` pende de
  `Turn` e `Turn` de `Session` — dois níveis. É `JOIN` com `GROUP BY`, não um
  laço.
- **"Mídia expirada" pode ficar mentindo.** Derivar de `created_at + retenção`
  é uma **previsão** da política do bucket, não uma leitura dela: o lifecycle do
  S3 apaga *"em até 24h depois"*, não no segundo exato. Decida se o campo
  significa "com certeza expirou" ou "provavelmente" — e escreva qual dos dois,
  porque a tela vai afirmar em português.

## Objetivo de aprendizado

Agregação no SQLAlchemy 2.0 async sem carregar entidade — `select(func.count())`
com `group_by` e `outerjoin`, e por que o `outer` importa aqui (sessão sem turn
some com o join interno). O equivalente mental é a diferença entre `GroupJoin` e
`Join` no LINQ, com a armadilha de que aqui o "some da lista" não dá erro: dá
uma linha a menos, em silêncio.
