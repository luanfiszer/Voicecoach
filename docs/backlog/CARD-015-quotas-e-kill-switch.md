# CARD-015 — Quotas + kill switch: bloqueante de lançamento comercial, com a unidade da cota decidida

- **ID:** CARD-015 · **Épico:** Fase 2 — Proteção de margem
- **Plataforma:** backend · **Esforço:** M · **Status:** backlog
- **Dependências:** CARD-010, CARD-014

## Contexto

ADR-0010 (teto duplo: console do provedor + aplicação) e a análise de custo §5,
que mudou o status deste card.

> **Números atualizados em 2026-08-27 pelo CARD-014**, que trocou a estimativa
> pelo custo **medido** (US$ 0,002678/turn) — ver
> [ADR-0051](../adr/0051-usage-event-fora-do-agregado-com-custo-congelado-na-escrita.md).

| Perfil | Turns/mês | Múltiplo — antes | Múltiplo — **medido** |
|---|---|---|---|
| Casual | 120 | 4,4× | **4,58×** |
| Engajado | 300 | 3,0× — no fio | **3,26×** — saiu do fio |
| Pesado | 900 | 1,49× | **1,66×** |
| Patológico | 3.000 | — | **0,61× — prejuízo líquido** |

**O custo medido melhora a conta, e não conserta a cauda.** O engajado saiu do
fio da navalha, mas o aluno de ~3.000 turns/mês continua dando **prejuízo
líquido** (margem −R$ 19,05). O que mudou foi só a distância até o prejuízo
começar — não o fato de ele existir.

**Sem cota, a margem continua sendo definida pelo usuário mais entusiasmado da
base.**

## Por que agora

**Repriorizado de higiene técnica para bloqueante de lançamento.** Estava na
Fase 5; com a monetização confirmada, ele passa a ser pré-requisito de qualquer
cobrança — vender assinatura sem cota é vender risco ilimitado por preço fixo.

## Problema — e uma decisão de produto embutida

Nada impede um loop descontrolado de gastar o orçamento do mês em horas.

E há uma divergência **medida** que este card tem de resolver (análise §8): o
domínio modelou a cota em **minutos falados** (`Turn.audio_duration`), mas o
custo é **por chamada ao LLM**:

| Aluno | Minutos | Turns | Custo total (medido, v2) |
|---|---|---|---|
| A — 100 turns de 6 s | 10 | 100 | **US$ 0,2113** |
| B — 20 turns de 30 s | 10 | 20 | US$ 0,0666 |

**Uma cota em minutos trata A e B como iguais, e A custa 3,17× mais.** Minutos é
a unidade que o **aluno** entende; turns é a que o **caixa** entende.

> **A divergência CRESCEU com o prompt v2** (era 3,0×, é 3,17× — análise §8
> recalculada pelo CARD-014), e o motivo é estrutural: o v2 aumentou a parcela de
> entrada, que é paga **por chamada**, independentemente do tamanho da fala. Cada
> token que o system prompt ganhar no futuro **aumenta** este número. O argumento
> a favor de um teto em turns fica mais forte com o tempo, não mais fraco.

> ✅ **DECIDIDO em 2026-08-27: cobrar e comunicar em minutos, limitar em ambos.**
> A cota comunicada é em **minutos** (o aluno entende), com um **teto de
> turns/dia** dimensionado para só morder no comportamento patológico. A
> comunicação não piora e o caixa fica protegido.
>
> **O ADR continua obrigatório** (critério 2 — afeta o domínio) e é escrito na
> execução deste card: o que foi decidido é a unidade, não o desenho. Duas
> consequências que o card tem de tratar e que a decisão não resolve sozinha:
>
> - **as duas cotas mordem em momentos diferentes do request.** Um teto em
>   **turns** é verificável **antes** de ler o corpo do upload; um teto em
>   **minutos** exige decodificar o áudio para conhecer a duração. Com as duas,
>   a ordem natural é: turns primeiro (barato, protege do loop), minutos depois
>   (caro, é o que o aluno vê);
> - **qual das duas o aluno vê quando o teto técnico morde?** A tela promete
>   minutos. Se o limite de turns recusar com 8 minutos ainda no saldo, a
>   mensagem tem de ser honesta sem expor mecânica — é requisito do
>   [CARD-033](CARD-033-saldo-de-cota-e-estado-do-servico.md), RF5.

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
- **O insumo já existe** (CARD-014): `UsageEventRepository.totals_for_student`
  devolve `StudentUsageTotals(turns, spoken, cost_usd, unpriced_turns)` para uma
  janela meio-aberta, somando **no banco** (`func.sum`/`func.count`), com o
  índice `(student_id, occurred_at)` já na ordem que esta consulta precisa. Ela
  foi desenhada para rodar **dentro do POST** — é a única query daquele card no
  caminho crítico de um request.
- **`unpriced_turns` não pode ser ignorado.** Um turn cujo modelo ficou fora da
  tabela de preços grava `estimated_cost_usd = NULL`, e a soma o **exclui**
  (ADR-0051). Tratar isso como custo zero faria o kill switch ler como grátis
  exatamente os turns que ninguém sabe precificar. Este card tem de decidir o que
  fazer quando `unpriced_turns > 0` — e a decisão vira ADR.
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
