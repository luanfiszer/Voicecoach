# CARD-015 — Quotas + kill switch: bloqueante de lançamento comercial, com a unidade da cota decidida

- **ID:** CARD-015 · **Épico:** Fase 2 — Proteção de margem
- **Plataforma:** backend · **Esforço:** M · **Status:** backlog
- **Dependências:** CARD-010, CARD-014

## Contexto

ADR-0010 (teto duplo: console do provedor + aplicação) e a análise de custo §5,
que mudou o status deste card:

| Perfil | Turns/mês | Múltiplo sobre custo |
|---|---|---|
| Casual | 120 | 4,4× |
| Engajado | 300 | **3,0×** — no fio |
| Pesado | 900 | **1,49×** |

**Sem cota, a margem é definida pelo usuário mais entusiasmado da base.** Um
aluno com ~3.000 turns/mês dá prejuízo líquido.

## Por que agora

**Repriorizado de higiene técnica para bloqueante de lançamento.** Estava na
Fase 5; com a monetização confirmada, ele passa a ser pré-requisito de qualquer
cobrança — vender assinatura sem cota é vender risco ilimitado por preço fixo.

## Problema — e uma decisão de produto embutida

Nada impede um loop descontrolado de gastar o orçamento do mês em horas.

E há uma divergência **medida** que este card tem de resolver (análise §8): o
domínio modelou a cota em **minutos falados** (`Turn.audio_duration`), mas o
custo é **por chamada ao LLM**:

| Aluno | Minutos | Turns | Custo total |
|---|---|---|---|
| A — 100 turns de 6 s | 10 | 100 | **US$ 0,183** |
| B — 20 turns de 30 s | 10 | 20 | US$ 0,061 |

**Uma cota em minutos trata A e B como iguais, e A custa 3× mais.** Minutos é a
unidade que o **aluno** entende; turns é a que o **caixa** entende.

> ⚠️ **Decisão pendente do desenvolvedor, e ela vira ADR** (critério 2 — afeta o
> domínio). A recomendação desta reconstrução: **cobrar em minutos, limitar em
> ambos** — a cota comunicada é em minutos (o aluno entende), com um teto de
> turns/dia dimensionado para só morder no comportamento patológico. Assim a
> comunicação não piora e o caixa fica protegido. **Não implementar antes do ok.**

## Proposta técnica

- Cota diária por student, **na unidade decidida acima**, verificada no POST do
  turn e consumida **só quando o turn entra na fila** (F11: erro de validação
  não consome).
- **Duas janelas diferentes, de propósito:** *rate limit* é janela deslizante; a
  **cota diária reseta por dia-calendário em fuso fixo** (a tela promete "renova
  às 00:00, horário de Brasília"). Os `TIMESTAMPTZ` do CARD-005 tornam isso
  possível.
- Kill switch global: contadores Redis `budget:daily` e `budget:monthly`
  (`INCR` do custo estimado ao completar o turn, alimentado pelo `UsageEvent` do
  CARD-014); excedido ⇒ POST de turn responde `503` Problem Details honesto até
  a janela virar.
- **Quota bloqueia escrita, não leitura**: com a cota estourada, revisar as
  correções do dia continua liberado.
- Rate limit por conta e por IP no POST.
- Atomicidade: `INCRBY` + verificação no mesmo passo (ou Lua), nunca
  get-then-set.

## Escopo

- **In:** cota por student, kill switch global, rate limit, testes de corrida.
- **Out:** entitlement por plano pago (CARD-023 — cota **técnica** e cota
  **comercial** são coisas diferentes: esta protege o caixa, aquela entrega o
  que foi vendido); UI de cota restante; alertas externos.

## Critérios de aceite

- **Dado** um student no limite diário, **quando** envia turn, **então** 429
  Problem Details com `retry_after` apontando a virada da janela **em fuso
  fixo** (não "24 h a partir de agora").
- **Dado** o budget mensal excedido, **então** todo POST de turn responde 503 e
  `GET /health` continua 200.
- **Dado** 10 POSTs concorrentes perto do limite, **então** a contagem não
  ultrapassa.
- **Dado** a cota estourada, **então** `GET /v1/turns/{id}` e o histórico
  continuam respondendo 200.

## Riscos

Corrida entre verificação e consumo (resolvida por operação atômica). E o risco
de produto: cota apertada demais mata o hábito que o produto precisa criar — o
número inicial é conservador **para cima**, e o `UsageEvent` diz depois se cabe.

## Objetivo de aprendizado

Padrões atômicos de Redis (`INCR`/`EXPIRE`, quando um script Lua é necessário) e
a diferença entre rate limit, quota e budget — três mecanismos que o protótipo
misturava num só módulo.
