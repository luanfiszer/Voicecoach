# CARD-023 — Gate de entitlement no POST de turn, com degradação honesta

- **ID:** CARD-023 · **Épico:** Fase 4 — Comercial (fecha a fase)
- **Plataforma:** backend (+ mensagem no cliente) · **Esforço:** P
- **Status:** backlog
- **Dependências:** CARD-015, CARD-020, CARD-022

## Contexto

O CARD-015 protege o **caixa** (kill switch e cota técnica). Este card entrega o
que foi **vendido**. São mecanismos diferentes, com mensagens diferentes ao
aluno, e confundi-los é como o protótipo misturava rate limit, quota e budget
num módulo só.

| Mecanismo | Protege | Mensagem ao aluno |
|---|---|---|
| Rate limit | o serviço | "calma, muitas requisições" |
| Kill switch (CARD-015) | o orçamento do fornecedor | "indisponível agora" (503) |
| **Entitlement (este card)** | o contrato com o aluno | "seu plano acabou / faça upgrade" |

## Por que agora

É o último elo entre "o produto roda em ~1,8 s" e "o aluno paga por isso". Sem
ele, o plano existe no banco e não significa nada na prática.

## Problema

O `POST /v1/sessions/{id}/turns` hoje não sabe o que o aluno comprou. E a
resposta de recusa precisa ser **honesta e distinguível**: o aluno que estourou
a cota do plano tem um caminho (upgrade); o que esbarrou no kill switch não tem
— só esperar.

## Proposta técnica

- Verificação do entitlement (derivado — CARD-020) no caso de uso do POST,
  **antes** de gravar áudio no storage: recusar depois de fazer upload é gastar
  banda e bytes para nada.
- **Códigos distintos**, em Problem Details: `402`/`403` com `type` próprio para
  entitlement (com o plano atual e o caminho de upgrade no corpo), `429` para
  cota, `503` para kill switch. Um cliente que trate tudo como "erro genérico"
  entrega a experiência errada.
- **Leitura continua liberada** (mesma regra do CARD-015): assinatura vencida
  não apaga o passado do aluno — histórico, correções e áudio já produzido
  continuam acessíveis. Bloquear o passado é hostil e, no limite, é problema de
  LGPD (dado dele).
- Período de carência do CARD-020 respeitado aqui, não reimplementado.
- Mensagem no cliente distinguindo os três casos.

## Escopo

- **In:** gate, códigos, degradação de leitura, testes.
- **Out:** telas de upgrade e checkout no app (canal — CARD-021); e-mail de
  cobrança falhada.

## Critérios de aceite

- **Dado** um aluno sem assinatura ativa e fora da carência, **quando** envia
  turn, **então** recebe o erro de entitlement (não 429, não 503) com o caminho
  de upgrade.
- **Dado** o mesmo aluno, **então** `GET` de histórico e de turns antigos
  continuam 200.
- **Dado** um aluno em carência (`past_due`), **então** o turn é aceito.
- **Dado** um aluno com plano ativo mas cota do plano estourada, **então** 429 —
  e a mensagem é diferente da de plano vencido.
- **Dado** a recusa, **então** nenhum byte de áudio foi gravado no storage.

## Riscos

Três mecanismos de bloqueio no mesmo endpoint, com ordem de avaliação que
importa. A ordem proposta — entitlement → cota → kill switch — é a mais barata
primeiro e a mais informativa para o aluno; precisa de teste que fixe a ordem,
senão ela muda sozinha na próxima refatoração.

## Objetivo de aprendizado

Modelar recusa como parte do contrato (Problem Details com `type` próprio), e o
caso de uso onde o `Result` do ADR-0017 finalmente morde: falha **esperada** de
negócio que não é bug — exatamente o gatilho escrito no `CLAUDE.md` para decidir
`Result` vs exceção.
