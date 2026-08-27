# Prompt — CARD-015: a cota deixa de ser palpite, e o caixa ganha um freio

- **Tipo:** prompt de sessão, complemento de `/executa-card 015`
- **Escrito em:** 2026-08-27, no fechamento do CARD-014 (PR #20)
- **Status:** não executado

> **Este prompt não substitui o `/executa-card`.** Aquele comando carrega o
> protocolo (branch, ordem de leitura, premissas antes do plano, DoD item a
> item, convenção de commit). **Rode `/executa-card 015` e leia isto junto** —
> aqui está o que é específico deste card, a arqueologia já feita, **o que o
> card assume e acabou de mudar** (§3.2), e as armadilhas que custam um card
> inteiro se descobertas tarde.

---

## 0. Antes do plano: a fila de perguntas está **vazia**

Pela regra em vigor (CLAUDE.md, reescrita pelo
[LEARNING-0005](../learnings/0005-a-fila-de-perguntas-nao-fecha-e-a-metade-nova-da-regra-ja-funciona.md)),
volta na abertura **só** a pergunta da sessão imediatamente anterior que ficou
sem desfecho. O CARD-014 não deixou nenhuma:

- as **três** decisões dele foram feitas no ponto da decisão, antes da primeira
  linha de código, e as três foram **respondidas**;
- a **Q15**, que voltava do CARD-013, foi **dispensada pelo desenvolvedor** e
  **arquivada com a evidência** — exatamente o caminho que a regra nova prevê
  para a segunda apresentação.

**Não reapresente nada.** Se você se pegar listando Q7/Q9/Q11/Q15, pare: todas
foram arquivadas, e só voltam quando um card tocar a decisão delas, refeitas **no
ponto da decisão daquele card**.

O que este card deve produzir são **perguntas novas**, no ponto da decisão, no
máximo duas — as duas mais caras de errar. Sugestões estão na §6.

---

## 1. Por que este é o próximo card

Ele já era o bloqueante de lançamento comercial. O que mudou ontem:

**O CARD-014 entregou o instrumento que este card consome.** Enquanto o custo era
estimativa, "quanto este aluno gastou hoje" era uma pergunta sem fonte. Agora
`usage_events` responde, e `UsageEventRepository.totals_for_student` **já foi
escrita pensando neste card** — soma no banco, janela meio-aberta, índice
`(student_id, occurred_at)` na ordem certa (igualdade antes de faixa).

**E o CARD-014 mexeu nos números que sustentam o card**, para os dois lados:

| | Antes | Medido (CARD-014) |
|---|---|---|
| Múltiplo no perfil **engajado** | 3,0x — no fio | **3,26x** — saiu do fio |
| Múltiplo no perfil **pesado** | 1,49x | **1,66x** |
| Aluno de ~3.000 turns/mês | prejuízo | **prejuízo (0,61x, −R$ 19,05)** |
| Divergência minutos vs. turns | 3,0x | **3,17x — cresceu** |

Duas leituras, e a segunda é a que importa:

1. **a margem melhorou, e isso não desarma o card.** O custo medido move a
   distância até o prejuízo; não elimina a cauda. Sem cota, a margem continua
   sendo definida pelo aluno mais entusiasmado da base;
2. **a divergência da unidade da cota CRESCEU, e vai continuar crescendo.** O
   prompt v2 aumentou a parcela de **entrada**, que é paga **por chamada**,
   independentemente do tamanho da fala. Cada token que o system prompt ganhar no
   futuro aumenta este número. **O argumento a favor de um teto em turns fica
   mais forte com o tempo, não mais fraco** — e isso é novo desde que o card foi
   escrito.

## 2. O que já está decidido e não se rediscute

- [**ADR-0010**](../adr/0010-politica-de-custo-projeto-pessoal.md) — **teto
  duplo**: console do provedor **e** aplicação. Este card é a segunda metade.
- [**ADR-0051**](../adr/0051-usage-event-fora-do-agregado-com-custo-congelado-na-escrita.md)
  — o custo por turn está gravado, congelado na escrita, e **preço desconhecido é
  `NULL`, nunca `0`**. Consequência direta para cá: `SUM` **exclui** essas
  linhas, e `StudentUsageTotals.unpriced_turns` existe justamente para que você
  não confunda "custo baixo" com "custo que não soubemos calcular".
- [**ADR-0039**](../adr/0039-result-minimo-para-desfecho-esperado-de-caso-de-uso.md)
  — cota estourada é **desfecho esperado do negócio**, logo `Err`, **não
  exceção**. A pergunta que separa os dois não é "deu erro?", é "quem chamou tem
  um bug?". Quem chamou não tem.
- [**ADR-0040**](../adr/0040-formato-de-erro-da-api-problem-details.md) — toda
  tradução para HTTP é Problem Details, num handler só. **Rota nunca monta
  `JSONResponse` de erro.** Você vai precisar de URNs novas em
  `api/schemas/problem.py` (`TYPE_VALIDATION`, `TYPE_SESSION_NOT_FOUND`… já
  existem lá; siga o padrão).
- [**ADR-0038**](../adr/0038-arq-entra-e-rebaixa-o-redis.md) — o `redis` está
  **fixado em 5.3.1** porque o `arq` exige `<6`. Confira a API que você for usar
  contra essa versão, não contra a documentação da 6.x.
- [**ADR-0013**](../adr/0013-configuracao-tipada-fora-das-camadas.md) —
  **`Decimal` para dinheiro, nunca `float`**. Leia a §4.2: esta regra tem um
  choque frontal com o Redis, e ele não é óbvio.
- [**ADR-0035**](../adr/0035-canal-worker-api-por-pubsub-com-o-banco-como-fonte-da-verdade.md)
  — **o banco é a fonte da verdade; o Redis é o caminho rápido.** Vale a pena ler
  antes de decidir onde o contador de budget mora (§4.1).

## 3. Arqueologia — verificada no repositório em 2026-08-27

### 3.1 O que já existe e você não precisa construir

- **`UsageEventRepository.totals_for_student(student_id, *, since, until)`**
  devolve `StudentUsageTotals(turns, spoken, cost_usd, unpriced_turns)`. Soma com
  `func.count`/`func.sum` **sem carregar entidade**, com `coalesce` para que
  aluno sem consumo devolva zeros e não `None`. Janela meio-aberta
  (`>= since`, `< until`), para que dois dias consecutivos não contem o mesmo
  turn duas vezes.
- **O índice `(student_id, occurred_at)`** já existe, e a ordem das colunas é
  deliberada: igualdade antes de faixa.
- **`Settings.daily_audio_minutes_per_student`, `daily_budget_usd` e
  `monthly_budget_usd`** já existem, os dois últimos em `Decimal`. Não invente
  campos novos ao lado deles sem motivo.
- **A borda já tem tudo**: `Result` com `match` + `assert_never` na rota,
  `ProblemError`, `app.state.redis` aberto no `lifespan` (uma conexão para o
  processo, nunca por request), `dependencies.py` com um provider por porta.

### 3.2 O que o card assume e **mudou desde que ele foi escrito**

| O card diz | A realidade em 2026-08-27 |
|---|---|
| *"alimentado pelo `UsageEvent` do CARD-014"* | O `UsageEvent` **existe**, e a consulta de agregação também. O que o card não previu é que agora há **duas** fontes possíveis para o mesmo número (Postgres e Redis) — e escolher entre elas é a decisão de §4.1 |
| *"múltiplo 3,0x no engajado, no fio"* | **3,26x** — saiu do fio. O card foi atualizado; a urgência dele **não** vem mais daí, vem da cauda (0,61x) |
| *"a divergência medida é de 3x"* | **3,17x**, e crescendo. O v2 aumentou a parcela por chamada |
| *"`INCR` do custo estimado"* | `INCR` é de **inteiro**; custo é `Decimal`. Ver §4.2 — este é o choque com o ADR-0013 |
| *"cota diária por student… verificada no POST"* | Verdade, mas **onde** no POST importa muito mais do que o card sugere. Ver §4.3 |

## 4. As armadilhas — o que o texto do card não antecipa

### 4.1 Duas fontes de verdade para o mesmo número, e o card pede as duas

O card pede contadores Redis (`budget:daily`, `budget:monthly`) **e** o
`UsageEvent` como alimentação. Mas o `UsageEvent` já responde a mesma pergunta,
direto do Postgres, com índice — e o ADR-0035 é explícito: **o banco é a fonte da
verdade, o Redis é o caminho rápido**.

A pergunta que o plano tem de responder: **quando os dois divergirem, quem
ganha?** Eles vão divergir — o Redis perde dados num restart sem persistência, e
o `INCR` acontece num processo (o worker) enquanto a linha nasce noutro.

Três desenhos possíveis, com o trade-off honesto:

| Desenho | O que ganha | O que perde |
|---|---|---|
| **Só Postgres** (`totals_for_student` no POST) | uma fonte de verdade, zero código de sincronia, o índice já existe | uma query por POST — medir se cabe no orçamento de latência da borda |
| **Só Redis** | rápido | contador que evapora num restart libera o gasto do mês inteiro; e reintroduz o float (§4.2) |
| **Redis como cache do Postgres** | rápido e recuperável | é o desenho com mais código, e a invalidação é onde os bugs moram |

**Nada disso está decidido.** É decisão de arquitetura, vira ADR (critério 2 e 5)
e deve ir ao desenvolvedor **antes** do código.

### 4.2 `INCR` de dinheiro reintroduz `float` — a regra que o CARD-014 acabou de defender

O card diz *"`INCR` do custo estimado"*. O `INCR` do Redis é de **inteiro**; para
somar `US$ 0,002678` a resposta natural é `INCRBYFLOAT` — e `INCRBYFLOAT` é
**ponto flutuante binário**, exatamente o que o ADR-0013 proíbe para dinheiro e
exatamente o que o CARD-014 existiu para não fazer.

Somar 3.000 turns por `INCRBYFLOAT` acumula erro num número que decide se o
produto para de atender. **Não é teórico: é a mesma classe de erro que o
`Decimal` do `estimated_cost_usd` foi escolhido para evitar, uma camada abaixo.**

A saída existe e é barata — contar em **micro-dólares como inteiro**
(`INCRBY` de `int(custo * 1_000_000)`) e converter só na leitura —, mas **é uma
decisão**, com uma escala escolhida, e ela precisa estar escrita. Repare que a
escala 8 do `NUMERIC(12,8)` e a escala 6 de micro-dólar **não são a mesma**: se
você escolher micro-dólar, decida o que acontece com as duas casas que sobram.

### 4.3 A verificação de cota chega tarde demais para proteger o que é caro

Olhe a ordem real do `POST /v1/sessions/{id}/turns` hoje
(`api/routes/turns.py`, `criar_turn`):

```python
extensao = extensao_para(audio.content_type)
bytes_do_aluno = await audio.read()          # o upload inteiro já subiu
duracao = await medir(bytes_do_aluno, ...)   # decodifica em executor — CPU
resultado = await handler.handle(StartTurn(...))
```

O `medir` **decodifica o áudio** para saber a duração, num executor, e o teto é
de 120 s de áudio (`max_turn_audio_duration`). Se a cota for verificada dentro do
`StartTurnHandler`, um aluno bloqueado **ainda** paga: o upload inteiro, a
decodificação e uma thread do pool — por turno, em loop, que é justamente o
cenário que o kill switch existe para conter.

**Isto inverte parte do desenho:** o freio precisa morder antes do trabalho caro,
mas a duração do áudio (insumo da cota em minutos) só é conhecida **depois** da
decodificação. As duas coisas não podem ser verdade ao mesmo tempo com uma
verificação só — e é aí que a escolha da unidade da cota (§6, D1) deixa de ser
decisão de produto e vira decisão de arquitetura:

- cota em **turns** é verificável **antes** de ler o corpo;
- cota em **minutos** exige decodificar primeiro.

Vale a pena olhar isso antes de escolher, não depois.

### 4.4 "Reseta às 00:00, horário de Brasília" não tem fuso em lugar nenhum

O card promete a virada por **dia-calendário em fuso fixo**, e o `_Timestamp` das
migrations é `TIMESTAMPTZ` exatamente para isso (o comentário em `models.py` diz
isso desde o CARD-005). Mas:

- **não existe campo de fuso na `Settings`.** Um `ZoneInfo("America/Sao_Paulo")`
  hardcoded numa camada errada é o tipo de coisa que passa em todo teste rodado
  em UTC e erra por três horas em produção;
- `zoneinfo` é **stdlib** desde o 3.9 (dispensa `pytz`), mas em algumas imagens
  Linux exige o pacote `tzdata`. Confira no container antes de confiar;
- o `retry_after` do critério de aceite aponta **a virada da janela**, não
  "24 h a partir de agora" — o que só é calculável com o fuso na mão.

### 4.5 O kill switch não pode derrubar o `/health`

O critério de aceite é explícito: *budget mensal excedido ⇒ POST responde 503 e
`GET /health` continua 200*. Um middleware global que barre tudo quebra isso —
e quebra de um jeito particularmente ruim, porque é justamente durante um kill
switch ativo que alguém vai querer que o health check responda.

O mesmo vale para o outro critério: **cota estourada não bloqueia leitura.**
`GET /v1/turns/{id}`, o histórico e o SSE continuam 200. Cota é sobre **gastar**,
não sobre **ver o que já foi pago**.

### 4.6 Rate limit por IP, atrás de um proxy, mede o proxy

O card pede rate limit *"por conta e por IP"*. Em desenvolvimento o backend fica
atrás do **ngrok**; em produção ficará atrás de algum proxy. O IP visto pelo
Starlette (`request.client.host`) é o do proxy — todos os alunos com o mesmo IP.
Usar `X-Forwarded-For` sem saber quem o escreve é pior: é um cabeçalho que o
cliente pode forjar, e um rate limit forjável não é um rate limit.

Decida explicitamente, e escreva: ou o rate limit por IP só existe quando houver
um proxy confiável declarado em config, ou ele não existe por enquanto e o de
conta basta.

### 4.7 O `Result` do `StartTurnHandler` vai crescer, e o `mypy` vai cobrar

Hoje a assinatura é `Result[TurnAccepted, SessionNotFound]`, e a rota faz `match`
terminando em `assert_never`. Acrescentar um desfecho de cota muda o `E` do
`Result` — e o `assert_never` **para de compilar** até a rota tratar o caso novo.

Isso é o mecanismo funcionando, não um obstáculo: é o ADR-0039 cobrando a
exaustividade. Vale ser a pergunta de previsão da sessão (§6).

## 5. Escopo — o que corta se estourar

- **Não corte:** a decisão da unidade da cota (é o ADR que o
  `docs/adr/README.md` lista como pendente há semanas), a atomicidade
  (`INCRBY` + verificação no mesmo passo, nunca get-then-set), o teste de corrida
  com POSTs concorrentes, e a virada da janela em fuso fixo.
- **Pode virar card próprio:** rate limit por IP (§4.6), se a decisão for
  "depende de proxy confiável"; UI de cota restante (já está em "Out");
  entitlement por plano (CARD-023).
- **Já está em "Out" e continua:** cota comercial. Cota **técnica** protege o
  caixa; cota **comercial** entrega o que foi vendido. Não são a mesma coisa e
  não moram no mesmo lugar.

## 6. Governança

1. **Decisão que os ADRs não cobrem vai ao desenvolvedor ANTES da primeira linha
   de código.** Nesta sessão são pelo menos quatro, e a primeira **bloqueia** o
   card inteiro:

   - **D1 — a unidade da cota** (minutos, turns, ou os dois). Está listada em
     `docs/adr/README.md` como *ADR pendente de decisão de produto*. A
     recomendação registrada no card é **cobrar em minutos, limitar em ambos**;
     leve o número novo junto (a divergência é 3,17x e **cresce**), e leve
     também a consequência de arquitetura da §4.3, que o card não conhecia;
   - **D2 — onde o contador de budget mora** (Postgres, Redis, ou Redis como
     cache) — §4.1;
   - **D3 — a representação do dinheiro no Redis**, se houver Redis —
     micro-dólar inteiro ou outra coisa — §4.2;
   - **D4 — o que fazer quando `unpriced_turns > 0`.** Um turn sem preço não
     entra na soma de custo. Ele conta para a cota? Bloqueia? É ignorado? Cada
     resposta tem um modo de falha diferente, e a pior é a silenciosa.

2. **A regra do explicador: no máximo 2 perguntas, no ponto da decisão, sobre
   consequência observável.** Candidatas boas, porque a resposta se confere
   rodando o comando na hora:

   - *"quando eu acrescentar um desfecho de cota ao `Result` do
     `StartTurnHandler` e **não** tocar na rota, o que quebra — `pytest` ou
     `mypy` —, em qual arquivo, e com que mensagem?"* (§4.7);
   - *"somando `0.002678` mil vezes com `INCRBYFLOAT` e com inteiro de
     micro-dólar, os dois totais batem? Qual é a diferença?"* (§4.2 — é uma
     demonstração de 5 linhas e mata a dúvida de vez).

3. **Item de ADR da DoD** — confira contra `docs/adr/README.md` e **cite o
   critério** (LEARNING-0003). Candidatos já visíveis: **critério 2** (a unidade
   da cota afeta o domínio; o contrato de erro ganha tipos novos), **critério 3**
   (é literalmente sobre custo recorrente), **critério 5** (a unidade da cota é
   caríssima de reverter depois de comunicada ao aluno).

4. **A skill `voicecoach-arquitetura` é de consulta obrigatória** (card de
   backend).

## 7. Definition of Done específica deste card

Além da DoD do `CLAUDE.md` e dos critérios de aceite do card:

- [ ] **A unidade da cota decidida e registrada em ADR**, fechando o item que
      `docs/adr/README.md` lista como pendente de decisão de produto.
- [ ] **Teste de corrida real**: N POSTs concorrentes perto do limite, e a
      contagem **não** ultrapassa. Não vale teste sequencial disfarçado — se a
      concorrência não for de verdade, o teste passa com get-then-set, que é
      exatamente o bug que ele existe para pegar.
- [ ] **`retry_after` apontando a virada da janela em fuso fixo**, provado com um
      relógio fixo — não "24 h a partir de agora".
- [ ] **`GET /health` continua 200** com o budget estourado, e **leitura de turn
      continua 200** com a cota estourada. Os dois com teste.
- [ ] **Nenhum `float` em caminho de dinheiro**, incluindo dentro do Redis.
- [ ] **A decisão sobre `unpriced_turns` escrita**, não implícita.
- [ ] Card atualizado e `docs/backlog/README.md` atualizado.

## 8. Restrições

- **Branch própria** a partir de `main` (com o CARD-014 mergeado — PR #20).
  `main` é protegida. **Confira `git branch --show-current` depois de criar a
  branch**: no CARD-011 dois commits caíram em `main` apesar de o `git switch -c`
  ter reportado sucesso.
- Commit **nunca** leva trailer `Co-Authored-By`
  ([LEARNING-0001](../learnings/0001-commit-com-coautoria-indesejada-do-agente.md)).
- **Não pushe nem abra PR sem perguntar.**
- **Custo: US$ 0,00 previstos.** Cota e budget são testáveis inteiramente com
  fakes e com linhas de `usage_events` inseridas à mão — nenhum critério de
  aceite exige chamar o provedor. Se algo parecer exigir, provavelmente é o teste
  que está desenhado errado.
- **A migration do CARD-014 (`c5e2a71b93d4`) já está aplicada** no banco de
  desenvolvimento. Rode `uv run alembic upgrade head` mesmo assim antes de testar
  à mão.

### Como subir o ambiente inteiro (conferido no CARD-014)

```bash
docker compose up -d
cd backend && uv run alembic upgrade head
(cd backend && uv run uvicorn voicecoach.api.app:create_app --factory --host 0.0.0.0 --port 8000 &)
(cd backend && uv run voicecoach-worker &)
```

> **Cuidado com processos velhos:** aconteceu no CARD-012, no CARD-013 **e de
> novo no CARD-014** — o `ps aux` daquela sessão achou um uvicorn e um worker de
> horas antes, servindo código antigo, que ninguém tinha subido naquela sessão.
> `ps aux | grep -E "uvicorn|voicecoach-worker"` antes de medir qualquer coisa, e
> derrube o que você subiu ao terminar.

---

- Responda em português. O desenvolvedor é **sênior em C#/.NET** e **iniciante
  em Python**: nada de explicar rate limit, quota ou budget como conceitos —
  ele conhece; o que interessa é **qual biblioteca/idioma de Python resolve o
  quê e por quê**. Pare para explicar em 3 linhas qualquer idioma sem paralelo
  em C# — neste card, provavelmente: `zoneinfo` e a aritmética de fuso da
  stdlib, o pipeline/script Lua do `redis-py` async (e por que `EVALSHA` é o
  jeito de tornar "verifica e incrementa" **um** passo), e a diferença entre
  `Depends` do FastAPI e um middleware ASGI — que é exatamente a diferença entre
  um freio que respeita o `/health` e um que não (§4.5).
