# CARD-020 — Planos, assinatura e entitlements no domínio

- **ID:** CARD-020 · **Épico:** Fase 4 — Comercial
- **Plataforma:** backend · **Esforço:** M · **Status:** backlog
- **Dependências:** CARD-015 (cota técnica), auth real (fase própria — não se
  cobra de um token fixo de dev)

## Contexto

A monetização por assinatura foi **confirmada pelo desenvolvedor em 2026-08-19**,
depois de estar registrada como premissa não confirmada na
[análise de custo §0](../analise-custo-e-precificacao.md). Ela contradiz o
objetivo escrito no `CLAUDE.md` e a política do ADR-0010 — daí a emenda proposta
na mesma sessão.

Âncoras de mercado (§6): Praktika ~US$ 8/mês (~R$ 44) é o teto da categoria de
conversa com IA. Com margem de 77% no casual e 33% no pesado, **preço único é
provavelmente subótimo** — dois planos separam melhor os perfis.

## Por que agora

É o primeiro card que transforma "o aluno paga" de premissa em modelo. E vem
**antes** da integração com provedor de pagamento de propósito: o domínio
precisa saber o que é um plano antes de alguém cobrar por ele, senão o modelo
nasce moldado pela API do gateway.

## Problema

O domínio não tem nenhum conceito de "o que este aluno comprou". Hoje só existe
cota técnica (proteção de caixa), que é outra coisa: ela protege o fornecedor,
não entrega o que foi vendido.

## Proposta técnica

- **`Plan`** (catálogo, versionado): nome, preço, moeda, e os **limites**
  (cota diária/mensal na unidade decidida no CARD-015). Plano é **versionado**
  porque preço muda e assinante antigo não pode ser reprecificado em silêncio.
- **`Subscription`**: `student_id`, `plan_version_id`, `status`, período atual
  (`current_period_start/end`, `TIMESTAMPTZ`), `cancel_at_period_end`.
  Estados: `trialing → active → past_due → canceled | expired`.
- **`Entitlement` é derivado, não persistido** — a mesma regra do ADR-0023: *"o
  que este aluno pode fazer agora"* é função de `Subscription.status` + período
  + plano. Persistir entitlement é criar uma segunda verdade que sai de
  sincronia exatamente quando dói (aluno pagou e não liberou).
- **`past_due` com carência** (grace period): pagamento falhado não corta acesso
  no mesmo instante — cartão recusado é fato comum, e cortar na hora é churn
  auto-infligido. Carência em config.
- Plano gratuito como `Plan` de verdade, com limite pequeno, e não como "ausência
  de assinatura" — assim o gate do CARD-023 tem um só caminho de código.

## Escopo

- **In:** entidades, estados, transições, entitlement derivado, migrations,
  testes de domínio.
- **Out:** cobrar (CARD-021); webhooks (CARD-022); enforcement (CARD-023);
  telas.

## Critérios de aceite

- **Dado** uma `Subscription` `active` dentro do período, **então** o
  entitlement libera; fora do período, não — sem job que "expire" nada.
- **Dado** `past_due` dentro da carência, **então** o acesso continua; passada a
  carência, não.
- **Dado** um `Plan` reprecificado, **então** o assinante antigo continua na
  versão que assinou (teste).
- **Dado** `cancel_at_period_end`, **então** o acesso vale até o fim do período
  já pago.
- Cobertura do núcleo ≥ 90% (ADR-0019).

## Riscos

Modelar assinatura é onde mais se copia o vocabulário do gateway. Se o modelo
começar a ter campo com nome de provedor, o desenho está errado — a integração é
adapter (CARD-021), não domínio.

## Objetivo de aprendizado

Modelar tempo em domínio Python: `TIMESTAMPTZ`, fuso e período de cobrança sem
`datetime.now()` espalhado — o equivalente de injetar um `TimeProvider`.
