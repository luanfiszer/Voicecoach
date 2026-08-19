# CARD-022 — Webhooks de pagamento: idempotência, reconciliação e o caminho triste

- **ID:** CARD-022 · **Épico:** Fase 4 — Comercial
- **Plataforma:** backend · **Esforço:** M · **Status:** backlog
- **Dependências:** CARD-021

## Contexto

O estado de uma assinatura muda **fora** do nosso sistema: renovação, cartão
recusado, cancelamento na loja, reembolso, upgrade. O provedor avisa por webhook
— e webhook é entregue **ao menos uma vez**, fora de ordem, e às vezes tarde.

Este projeto já sabe disso por experiência: o protótipo tinha webhook do Twilio
sem validação de assinatura e sem idempotência por `MessageSid` (F1/F2 e F4 do
diagnóstico). O canal morreu; a lição, não.

## Por que agora

É o card que faz a `Subscription` do CARD-020 continuar verdadeira depois do
primeiro dia. Sem ele, o aluno cancela e continua com acesso — ou paga e perde.

## Problema

Três problemas que webhook sempre traz, e um específico daqui:

1. **Autenticidade** — endpoint público que muda estado de cobrança.
2. **Duplicidade e ordem** — o mesmo evento chega duas vezes; o "cancelado"
   chega antes do "renovado".
3. **Perda** — se o webhook não chegar, ninguém percebe.
4. **Duas fontes de verdade** — o provedor tem a dele, nós temos a nossa.

## Proposta técnica

- **`POST /v1/billing/webhook`**: valida a assinatura do provedor **antes** de
  qualquer parse; assinatura inválida ⇒ 401 e nada é processado.
- **Idempotência pelo id do evento do provedor**, persistida (não só Redis: um
  evento de cobrança reprocessado por expiração de TTL é dinheiro).
- **Ordem por versão/timestamp do evento, não por ordem de chegada:** evento
  mais velho que o estado atual é **descartado explicitamente e logado**, nunca
  aplicado.
- **Processamento fora do request:** o handler valida, persiste o evento cru e
  enfileira (`arq`, ADR-0005). Responder rápido é requisito do provedor; e o
  evento cru guardado é o que permite reprocessar depois de um bug.
- **Reconciliação periódica** — job diário que compara nosso estado com o do
  provedor para as assinaturas que mudam de período naquele dia. É o que cobre o
  problema 3, que nenhuma quantidade de cuidado no handler resolve.
- **Divergência é logada e resolvida a favor do provedor** — ele é quem tem o
  dinheiro. Mas a divergência **é registrada**, porque divergência recorrente é
  bug nosso.

## Escopo

- **In:** endpoint, validação, idempotência persistida, ordenação, fila,
  reconciliação, testes com eventos gravados do provedor.
- **Out:** enforcement (CARD-023); disputa/chargeback (fora do horizonte);
  e-mails transacionais.

## Critérios de aceite

- **Dado** um webhook com assinatura inválida, **então** 401 e nenhum estado
  muda (testado com payload legítimo e assinatura trocada).
- **Dado** o mesmo evento entregue 3 vezes, **então** o estado muda uma vez.
- **Dado** um evento mais antigo que o estado atual, **então** é descartado e
  logado — o estado **não** regride.
- **Dado** um evento de renovação, **então** `current_period_end` avança e o
  entitlement (derivado, CARD-020) acompanha sem job nenhum.
- **Dado** um estado divergente do provedor, **quando** a reconciliação roda,
  **então** o nosso converge e a divergência é registrada.

## Riscos

Testar cobrança de verdade é caro e lento. Mitigação: eventos gravados do modo
de teste do provedor como fixture — e um teste de reconciliação que não depende
de rede.

## Objetivo de aprendizado

Idempotência e ordenação em integração com terceiro — a diferença entre "recebi
o evento" e "o estado está certo", e por que a segunda precisa de um job que não
confia na primeira.
