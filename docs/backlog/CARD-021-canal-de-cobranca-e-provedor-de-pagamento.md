# CARD-021 — Canal de cobrança e integração com o provedor de pagamento

- **ID:** CARD-021 · **Épico:** Fase 4 — Comercial
- **Plataforma:** backend (+ cliente do canal escolhido) · **Esforço:** G
- **Status:** **bloqueado — aguarda ADR de canal de cobrança**, e desde
  2026-09-10 é **bloqueante da V1.0** (N2 do corte de lançamento)
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

## Atualização de 2026-09-10 — o que mudou, e o que a pesquisa precisa responder

Este card foi escrito em 2026-08-19 supondo Fase 4 e loja adiada. **Duas
decisões de 2026-09-10 o promoveram a bloqueante da V1.0:** App Store pública e
cobrança já no lançamento. O desenvolvedor escolheu, no mesmo dia, **decidir o
canal depois da pesquisa** — então a pesquisa deixa de ser pré-requisito informal
e vira **o primeiro entregável deste card**.

### Uma correção ao que foi dito nesta sessão

Foi afirmado, ao montar o corte da V1.0, que a App Store **impõe** o IAP e
portanto "resolve o ADR por imposição". **Isso está errado e a correção importa,
porque muda a decisão:** o que a regra exige é que a compra feita *dentro* do
app use IAP. **Vender apenas na web continua permitido** — é o padrão de
"serviços multiplataforma", em que o app apenas *consome* uma assinatura obtida
fora dele. O preço disso não é legal, é de conversão: não se pode divulgar a
compra externa dentro do app.

Ou seja: **os 11–26 pontos de margem continuam em jogo**, e a escolha deste card
continua real.

### Correções de número

- A comissão relevante é **15%**, não 30%: abaixo de US$ 1M/ano vale o programa
  para pequenos negócios. A conta de ~R$ 3,30/usuário/mês da análise de custo já
  usava 15% e continua válida.

### As perguntas que a pesquisa tem de fechar

**Aviso sobre a fonte:** esta área mudou bastante nos últimos tempos e **varia
por jurisdição** (decisões judiciais e regulatórias nos EUA, na União Europeia e
no Brasil alteraram o que se pode fazer quanto a *link-out* e divulgação). Nada
aqui deve ser aceito de memória — **a pesquisa confere contra a documentação
vigente da Apple**, e registra a data da consulta no ADR, porque a resposta tem
prazo de validade.

1. **O que exatamente se pode dizer dentro do app** sobre uma assinatura vendida
   fora dele, hoje, para um app distribuído no Brasil. É a pergunta que decide se
   "só web" é um canal viável ou um beco.
2. **Se o *link-out* é permitido** para este caso e sob que condições — e com
   qual comissão, já que em alguns regimes ele não é isento.
3. **O que muda no fluxo de assinatura** quando ela é vendida fora: como o app
   descobre que o aluno é assinante (é o CARD-023, o gate de entitlement) sem
   que a loja considere isso uma compra escondida.
4. **O que a Apple exige do app mesmo no cenário "só web"** — notadamente
   restauração de compra e o que mostrar a um usuário não assinante.
5. **Qual é o caminho mais curto até lançar.** Não é a mesma pergunta que "qual
   dá mais margem", e o corte da V1.0 diz que os dois canais juntos **dobram** o
   CARD-022 (duas reconciliações, dois estados de assinatura em sincronia).

### Os três desenhos, agora nomeados

| Canal | Comissão | Custo de construir | Risco |
|---|---|---|---|
| **Só IAP** | 15% | menor — um provedor, um webhook | nenhum de regra; é o caminho que a loja quer |
| **Só web** | ~4% | médio — gateway + o app tendo de descobrir o assinante sem vender | **de conversão**: produto sem marca, compra que o usuário precisa achar sozinho |
| **Os dois** | mista | **maior** — dobra o CARD-022 | de sincronia: duas fontes achando que são donas do mesmo estado |

**Recomendação técnica, e ela não decide por você:** para a V1.0, **só IAP** é o
caminho mais curto e o de menor risco de regra — e migrar para web depois é
aditivo, enquanto o contrário obriga a desfazer. Os 11 pontos de margem são
reais, mas margem sobre zero assinante é zero.

## Critérios de aceite

- **Dado** a pesquisa concluída, **então** cada uma das cinco perguntas acima
  tem resposta escrita **com a fonte e a data da consulta** — resposta sem data
  não vale, porque a regra muda.
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
