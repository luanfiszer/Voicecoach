# ADR-0063 — Cota diária por student em minutos e turns, kill switch global por custo

- **Status:** aceito
- **Data:** 2026-09-13
- **Critério de obrigatoriedade** (`docs/adr/README.md`): **2 — define ou altera
  uma fronteira** (o caso de uso `StartTurn` ganha dois desfechos novos no
  `Result`, contrato de erro da API) e **3 — afeta custo recorrente** (é o
  mecanismo que limita o gasto por aluno e por conta do produto).
- **Relacionado:** ADR-0010 (política de custo), ADR-0051 (`UsageEvent`,
  `estimated_cost_usd` nulo para modelo sem preço), CARD-014 (custo medido),
  CARD-033 (saldo de cota na tela, consumidor deste card)

## Contexto

A análise de custo (§8) mediu uma divergência de **3,17×** entre cobrar por
minuto falado (o que o aluno entende) e o custo real, que é por **chamada ao
LLM** — dominado pela parcela de entrada do prompt, paga por turn
independentemente da duração da fala. Sem cota, a margem do produto é definida
pelo aluno mais entusiasmado da base, e o perfil "patológico" (≈3.000
turns/mês) já dá **prejuízo líquido** medido.

**Decidido com o desenvolvedor em 2026-08-27** (registrado no CARD-015): cobrar
e comunicar em **minutos** (unidade que o aluno entende), e limitar em
**minutos e turns**, o segundo como teto técnico dimensionado para só morder
no comportamento patológico. Este ADR formaliza o desenho que executa essa
decisão e resolve o que ficou em aberto: o que fazer com turns cujo modelo
ficou fora da tabela de preços (`unpriced_turns`, ADR-0051), e o desenho do
kill switch global que já tinha configuração parada no `config.py`
(`daily_budget_usd`, `monthly_budget_usd`, `daily_audio_minutes_per_student`)
sem nenhum código que os lesse.

## Decisão

**Três mecanismos independentes, cada um resolvendo um risco diferente:**

1. **Cota diária por student, em minutos falados E em turns**, verificada no
   `POST /sessions/{id}/turns` via `UsageEventRepository.totals_for_student`
   (já existente, CARD-014) contra a janela `[meia-noite de hoje, meia-noite de
   amanhã)` **em fuso fixo `America/Sao_Paulo`** — a mesma janela que a tela
   promete ("renova às 00:00, horário de Brasília"). Qualquer um dos dois
   tetos excedido responde `429` com `reset_at` apontando a próxima meia-noite
   nesse fuso — nunca "24h a partir de agora", que seria uma janela deslizante
   disfarçada de calendário.
2. **Kill switch global por custo**, em dois contadores Redis
   (`voicecoach:budget:daily:{data}` e `voicecoach:budget:monthly:{ano-mes}`,
   em **centavos de dólar**, `INCRBY` inteiro — dinheiro não é `float`).
   Alimentados pelo `ProcessTurnHandler` no mesmo ponto em que grava o
   `UsageEvent`: soma o `estimated_cost_usd` do turn que acabou de terminar.
   Comparados contra `daily_budget_usd`/`monthly_budget_usd` (`config.py`,
   já existentes) no `POST`; excedido responde `503` Problem Details — **é
   falha do serviço para o cliente, não do aluno** (`GET /health` continua
   200, o histórico continua acessível).
3. **Rate limit por student e por IP**, independente dos dois acima: protege
   contra um *loop* de cliente disparando POSTs, não contra o custo agregado.
   Fixed window de 1 minuto, `INCR`+`PEXPIRE` atômicos via script Lua (o que
   o `redis-py` executa com `EVAL`) — nunca get-then-set, que tem corrida
   entre o `GET` e o `SET`. É checado **antes** de ler o corpo do upload
   (dependência do FastAPI, não dentro do caso de uso), e é o único dos três
   que não precisa saber quem é o aluno para negar cedo.

**`unpriced_turns` não exige tratamento especial na cota por student.** A
agregação de `totals_for_student` já conta turns e minutos **independente do
preço** (`func.count()`/`func.sum(stt_audio_duration)` não filtram por
`estimated_cost_usd`) — um turn sem preço morde a cota de minutos e de turns
exatamente como qualquer outro. A lacuna real é só no kill switch em
**dólares**: um turn sem preço soma **zero** ao contador Redis, porque não há
valor a somar — o mesmo limite já aceito pelo ADR-0051 para a soma de custo no
banco. Registrado como risco residual, não como decisão pendente: um surto de
turns de modelo sem preço ainda é contido pelo teto de **turns**, só não conta
para o teto de **dólares**.

**Números iniciais, conservadores para cima** (Riscos do CARD-015: cota
apertada mata o hábito antes de o produto provar valor):

| Config | Valor | Já existia? |
|---|---|---|
| `daily_audio_minutes_per_student` | 10 min | sim (`config.py`, sem uso) |
| `daily_quota_turns_per_student` | 60 | **novo** |
| `daily_budget_usd` | US$ 1,00 | sim (`config.py`, sem uso) |
| `monthly_budget_usd` | US$ 10,00 | sim (`config.py`, sem uso) |
| `turn_rate_limit_window` | 1 min | **novo** |
| `turn_rate_limit_per_student` | 20/min | **novo** |
| `turn_rate_limit_per_ip` | 60/min | **novo** |

60 turns/dia cobre folgadamente o perfil "pesado" (≈30/dia) sem deixar o
"patológico" (≈100/dia) passar batido. Todos os seis números são estimativa a
recalibrar com a distribuição real do `UsageEvent` — a mesma disciplina do
`stt_min_confidence` do ADR-0057.

## Alternativas consideradas

### Alternativa A — só teto de turns (sem minutos)

Mais simples de verificar (não depende de decodificar áudio). Rejeitada: a
tela promete minutos ao aluno (decisão de produto de 2026-08-27); comunicar em
turns seria expor mecânica de custo interna numa métrica que ninguém entende
("você tem 40 turns restantes" não significa nada para quem não sabe que o
produto cobra por chamada).

### Alternativa B — só teto de minutos (sem turns)

Rejeitada pela divergência medida de 3,17×: um aluno que manda 100 falas de 6s
custa o mesmo em minutos que 20 falas de 30s, mas **3,17× mais** em dinheiro —
um teto só em minutos não protege contra exatamente o padrão de abuso mais
barato de produzir (muitas falas curtas).

### Alternativa C — janela deslizante para o reset da cota, em vez de calendário fixo

Tecnicamente mais simples num contador Redis único (`INCR`+`EXPIRE` de uma
vez, sem calcular meia-noite). Rejeitada: quebraria a promessa já feita ao
aluno ("renova às 00:00") — um aluno que gasta a cota às 23h veria o reset "às
23h de amanhã", não à meia-noite, e a tela estaria mentindo por construção.

## Consequências

- **Positivas:** a margem deixa de depender do aluno mais entusiasmado da
  base; o kill switch protege o orçamento mensal inteiro, não só por aluno; o
  `UsageEvent` (já instrumentado desde o CARD-014) alimenta os três mecanismos
  sem nenhuma coluna nova — nenhuma migration neste card.
- **Negativas:** três mecanismos independentes são três lugares para calibrar
  e três testes de corrida a manter. Um aluno no teto técnico de turns antes
  de esgotar os minutos (a divergência de 3,17× torna isso plausível para
  quem fala pouco por turn) recebe uma recusa cuja mensagem a tela do
  CARD-033 precisa explicar sem mencionar "turns" — dívida de UX explícita
  para aquele card. O kill switch global por custo tem o residual já descrito:
  turns sem preço não contam para ele.
- **Equivalente mental .NET:** os três mecanismos são três `IRateLimiter`
  diferentes num pipeline de middleware — um por conta (sliding/fixed window
  sobre contagem), um por IP (idem), e um circuit breaker de aplicação que
  soma custo em vez de contar falhas. O Redis fazendo a atomicidade via script
  Lua é o paralelo de um `INCR` atômico do `IDistributedCache` que .NET não
  oferece nativamente — de lá para cá seria implementar a mesma coisa sobre
  Redis via `StackExchange.Redis` com `ScriptEvaluateAsync`.
