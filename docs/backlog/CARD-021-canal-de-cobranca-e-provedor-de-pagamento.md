# CARD-021 — Canal de cobrança e integração com o provedor de pagamento

- **ID:** CARD-021 · **Épico:** Fase 4 — Comercial
- **Plataforma:** backend (+ cliente do canal escolhido) · **Esforço:** G
- **Status:** **bloqueado — aguarda ADR de canal de cobrança**
- **Dependências:** CARD-020; **ADR pendente** (canal + provedor)

## Contexto

A [análise de custo §4 e §10](../analise-custo-e-precificacao.md) achou o item
mais caro do produto, e não é IA:

| Canal | Comissão | Peso |
|---|---|---|
| App Store / Google Play | **15%** (< US$ 1M/ano), 30% acima | **~4× o custo de IA por usuário** |
| Web (Pix/cartão) | ~4% | — |

Vender pela web em vez de dentro do app recupera **~R$ 3,30/usuário/mês** —
quase o custo de IA inteiro de um aluno engajado. **11 a 26 pontos de margem**
dependem desta escolha.

Consequência de desenho: o app web do ADR-0002 **deixa de ser companion e vira
candidato a canal de receita** — o que muda a prioridade dele no roadmap.

## Por que agora

Porque é a decisão de maior impacto financeiro do produto inteiro, e porque ela
molda o CARD-022 (webhook de loja e webhook de gateway não se parecem) e o
próprio roadmap da web.

## Problema — e por que este card está bloqueado

Duas coisas precisam ser resolvidas **antes** de escrever código, e nenhuma é
técnica:

1. **O canal.** Loja (mais conversão, menos margem, obrigatório para certos
   fluxos) vs. web (mais margem, mais atrito, regras de *steering* das lojas).
2. **A restrição a verificar, não a supor:** as regras da App Store limitam
   divulgar cobrança externa **dentro** do app. Isso é **pesquisa a fazer** —
   está registrado como incerteza desde a análise de custo §10 e continua sem
   resposta.

**Isto vira ADR (critérios 1 e 3: dependência externa e custo recorrente), e o
ADR precisa da decisão do desenvolvedor.** O card não começa antes.

## Proposta técnica — os dois desenhos, para a decisão ser informada

**Se for loja:** `RevenueCat` sobre StoreKit 2 / Play Billing. Ele existe porque
validar recibo, sincronizar estado entre as duas lojas e lidar com renovação é
trabalho que ninguém quer fazer duas vezes; o equivalente mental é uma fachada
sobre dois SDKs de plataforma com validação server-side. O backend continua dono
da `Subscription` (CARD-020) e o provedor é fonte do **evento**, não da verdade.

**Se for web:** gateway com Pix e cartão. Stripe cobre Pix no Brasil e tem a
melhor documentação e o melhor modelo de testes; Mercado Pago/Asaas/Pagar.me
tendem a ganhar em taxa e em suporte local. **Critério de desempate proposto:**
qualidade do fluxo de webhook e do modo de teste — porque o CARD-022 é onde os
bugs de cobrança realmente moram.

**Em qualquer cenário, a porta é `PaymentProvider`** (`create_checkout`,
`fetch_subscription_state`, `cancel`) — nenhum tipo do SDK vaza para
`application`. Trocar de provedor é adapter novo, como o ADR-0012 manda.

## Escopo

- **In:** ADR de canal + provedor; porta; adapter; fluxo de checkout do canal
  escolhido.
- **Out:** webhooks e reconciliação (CARD-022); enforcement (CARD-023);
  impostos e nota fiscal (fora do horizonte — registrar como pendência real).

## Critérios de aceite

- **Dado** o ADR aceito, **então** o card sai de bloqueado com canal e provedor
  nomeados e o motivo escrito.
- **Dado** um checkout no modo de teste do provedor, **então** a `Subscription`
  do CARD-020 nasce `active` com período correto.
- **Dado** o adapter, **então** nenhum tipo do SDK aparece em `application`
  (verificado por `lint-imports`).

## Riscos

- **Regra de loja descoberta tarde** é o risco caro: pode invalidar o canal
  escolhido depois da implementação. Por isso a pesquisa é pré-requisito do ADR,
  não tarefa do card.
- Cobrar dinheiro de verdade tem caminho triste próprio (chargeback, reembolso,
  disputa) que este card **não** cobre e o CARD-022 só encosta.

## Objetivo de aprendizado

Integração de pagamento como adapter: onde mora o estado da verdade quando um
terceiro também acha que é dono dele.
