# LEARNING-0009 — O loop mergeou, com todos os gates verdes, dois defeitos que só o uso real mostrava

- **Data:** 2026-10-01
- **Card/sessão relacionado:** validação do loop autônomo de 2026-09-13 (CARDs
  049–060), feita a pedido do desenvolvedor antes de continuar o loop. Gerou o
  CARD-062 e partes do CARD-060 (retomada).

## Sintoma

Um roteiro de QA contra a stack real (API + worker + Postgres/Redis/MinIO,
`uvicorn` de verdade, chamadas HTTP de verdade) achou, em minutos, dois
defeitos graves que estavam em `main` com CI verde e 653 testes passando:

1. **Todo cadastro por e-mail falhava** (CARD-049). O SQLAlchemy inseria
   `credentials` antes de `students` no mesmo commit, a FK recusava, e o erro
   era traduzido como "e-mail já existe" — que responde `202` de propósito
   (anti-enumeração). Nenhum log, nenhuma resposta de erro: a conta só não
   existia.
2. **Isolamento entre alunos ausente em quatro rotas.** `GET /v1/turns/{id}`
   e o SSE não pediam token nenhum (`Bearer lixo` → `200` com a transcrição e
   o áudio de outro aluno); `POST .../turns` e `POST .../end` aceitavam a
   sessão de qualquer aluno.

E um terceiro, de outra natureza: `alembic check` acusava 8 operações de
drift entre `models.py` e as migrations.

## Causa raiz

**Os testes verificavam o que o autor imaginou, e o que o autor imaginou era
um mundo com um aluno só.**

- *Por que o cadastro passou?* Todo teste de persistência usava a fixture
  `aluno_isolado`, que comita o `Student` **antes** de o teste inserir a
  `Credential`. O caminho real (`Student` + `Credential` no mesmo flush) nunca
  rodou contra Postgres. Os testes de rota usam fakes em memória, que não têm
  FK.
- *Por que o IDOR passou?* O fixture `app` sobrescreve
  `requesting_student_id` com uma constante `ALUNO` para todas as rotas.
  Nenhum teste de rota rodava a autenticação de verdade, e quase nenhum criava
  um **segundo** aluno. Quando o CARD-049 trocou a constante `DEV_STUDENT_ID`
  pelo token, ele migrou "todas as rotas que já dependiam de
  `requesting_student_id`" — e as que nunca tinham dependido (porque antes do
  login não havia dono a checar) ficaram de fora sem que nada reclamasse. A
  regra de dono existia (RNF2, `DiscardTurn`), mas era aplicada rota a rota,
  de memória.
- *Por que ninguém notou?* O loop autônomo fechava cada card pelos gates
  (lint, tipo, cobertura, testes). Nenhum gate exercita **o gesto do usuário
  na stack real**. O CARD-049 até registra um fluxo ponta a ponta — mas contra
  o ambiente onde o defeito 1 não se manifestava, ou antes de o defeito 2
  existir como risco (com um aluno só, não há "outro aluno").

## Como descobri

Pedido explícito de "validar tudo antes de continuar". O roteiro foi escrito
pelo gesto, não pelo código (LEARNING-0007): o que um aluno faz do cadastro ao
delete, mais o que um **segundo** aluno tentaria. Cada passo com um `checa()`
explícito e a resposta impressa quando falha. O defeito 2 apareceu no passo
"token inválido → 401", posto ali por desconfiança, não por suspeita. O
defeito 1 reapareceu de graça quando o QA rodou numa branch saída de `main`
sem a correção — mesma assinatura (`202` e login `401`).

## Como evitar

1. **Teste de rota de recurso do aluno tem sempre dois casos a mais:** sem
   token (com o `requesting_student_id` real, sem override) → `401`; recurso
   de **outro aluno** → o mesmo `404` do inexistente.
2. **Card de backend que muda fluxo de usuário fecha com QA contra a stack
   real**, com o roteiro e a saída colados no card — não só com a suíte. A
   suíte usa fakes por bons motivos (ADR-0018); exatamente por isso ela não
   substitui a execução real.
3. **`alembic check` virou teste** (`test_models_e_migrations_nao_divergem`).

## Regra criada no CLAUDE.md

**Proposta — PENDENTE DE APROVAÇÃO do desenvolvedor** (o `/postmortem` exige
aprovação antes de editar o CLAUDE.md; não aplicada). Entraria em "Regras de
trabalho", consolidando com a regra do LEARNING-0007 (as duas dizem
"reproduza pelo gesto, não pelo código"):

> - **Gesto real antes de fechar, e sempre com dois alunos** (origem:
>   [LEARNING-0007], [LEARNING-0009]): bug relatado por uso se reproduz pelo
>   gesto, não pelo código — liste todo controle que o relato pode nomear e
>   reproduza cada um no ambiente do relato. E card de backend que toca fluxo
>   de usuário só fecha com **QA contra a stack real** (API e worker de
>   verdade, roteiro e saída colados no card). Toda rota que recebe id de
>   recurso do aluno tem teste de **sem token → 401** (sem override de auth)
>   e de **outro aluno → mesmo 404 do inexistente**. Gates verdes provam que o
>   código é coerente consigo mesmo, não que o produto funciona.

O roteiro usado está registrado no CARD-062 como ponto de partida.
