# Prompt — CARD-025: o turn que morre calado ganha quem o declare morto

- **Tipo:** prompt de sessão, complemento de `/executa-card 025`
- **Escrito em:** 2026-08-27, na sessão que varreu o guia arquitetural e o design
- **Status:** **executado em 2026-08-29** (branch `card-025-varredura-de-turns-travados`)

> **Resultado da §3.3: deu 1.** O `arq` não retenta exceção comum — o card ganhou
> o segundo problema que o prompt previa, e ele era maior que o original. O
> desfecho está no [ADR-0052](../adr/0052-o-retry-do-arq-e-explicito-e-a-marcacao-de-falha-mora-num-lugar-so.md).
> **A §4.5 e o objetivo de aprendizado saíram INVERTIDOS:** `cron_jobs` com
> `unique=True` (o default) executa **uma vez** com N réplicas, não N.

> **Este prompt não substitui o `/executa-card`.** Aquele comando carrega o
> protocolo (branch, ordem de leitura, premissas antes do plano, DoD item a
> item, convenção de commit). **Rode `/executa-card 025` e leia isto junto** —
> aqui está a arqueologia já feita, **uma investigação que vem antes do plano**
> (§3.3) e que pode mudar o card, e as armadilhas que custam a sessão.

---

## 0. Antes do plano: a fila de perguntas está **vazia**

Última sessão executada: **CARD-014** (PR #20). Ela não deixou pergunta sem
desfecho — as três decisões foram feitas no ponto da decisão e respondidas, e a
Q15 foi **dispensada pelo desenvolvedor** e arquivada com evidência.

Depois dela houve duas sessões de **backlog** (PRs #22 e #23), que não executam
card e não produzem pergunta de explicador.

**Não reapresente Q7/Q13/Q14.** Estão arquivadas e só voltam quando um card tocar
a decisão delas. Este não toca.

---

## 1. Por que este card, e por que ANTES do CARD-026

Ele estava parado como dívida da Fase 1 desde o CARD-009 (*"se estourar, o corte
é a varredura de travados"*). Três coisas o trouxeram para a frente:

**1. O caminho de falha mais provável do produto não tem quem o feche.** Ver
§3.3 — é o motivo principal e ele é novo.

**2. Ele é rede de segurança para o card seguinte.** O CARD-026 vai mexer em
timeout, retry e circuit breaker: durante aquela sessão, turns **vão** falhar de
formas novas. Fazer isso com a varredura já no lugar é a diferença entre ver a
falha e ficar olhando uma tela de espera sem saber se o bug é seu.

**3. Dois cards novos dependem dele** — o CARD-032 ("Descartar", a ação manual
sobre o mesmo turn travado) e o CARD-034 (encerramento automático de sessão, que
é literalmente o mesmo mecanismo aplicado a outra entidade). O que você decidir
aqui sobre onde mora um job periódico, os dois herdam.

## 2. O que já está decidido e não se rediscute

- [**ADR-0023**](../adr/0023-ciclo-de-vida-do-turn-com-entrega-em-cascata.md),
  item 6 — **falhar não apaga trecho.** É a invariante mais fácil de quebrar sem
  que nenhum teste de status perceba: o aluno já ouviu duas frases, e o registro
  tem de continuar dizendo que ele ouviu. `Turn.fail()` já respeita isso.
- [**ADR-0037**](../adr/0037-a-cascata-e-uma-fila-interna-com-um-consumidor-so.md)
  — **nada de reprocessar depois de entrega parcial.** A varredura **marca
  falho**; ela não retenta. Se você se pegar escrevendo "e então reenfileira",
  parou.
- [**ADR-0035**](../adr/0035-canal-worker-api-por-pubsub-com-o-banco-como-fonte-da-verdade.md)
  — o banco é a verdade, o Redis é o caminho rápido. Publicar o evento `failed`
  é cortesia para quem está com o stream aberto; quem chegar depois descobre
  pelo `GET`. **Falha ao publicar não pode desfazer a marcação.**
- [**ADR-0025**](../adr/0025-modelos-residentes-no-worker-e-readiness-que-distingue-pronto.md)
  — `MAX_JOBS = 1` **não é limitação técnica**: STT e TTS disputam a mesma CPU.
  Não suba isso para "a varredura não atrapalhar".
- [**ADR-0016**](../adr/0016-ciclo-de-vida-do-turn-estado-grosso-e-etapa-derivada.md)
  / [**0028**](../adr/0028-derivacao-da-etapa-do-turn-mora-no-dominio.md) — não
  persistir o que se deriva. Não crie coluna `is_stale` nem `swept_at` sem
  motivo escrito.

## 3. Arqueologia — verificada no repositório em 2026-08-27

### 3.1 O que já existe e você não constrói

- **`Turn.fail(reason, now)`** (`domain/turn.py:374`) aceita a partir de
  `queued` **e** de `processing`, de propósito, e o docstring diz que é isso que
  *"dá dono ao 'demorou mais que o normal' da tela de timeout"*. Ele levanta se
  o turn já é `completed` ou `failed` — o que é a sua proteção contra corrida.
- **A receita completa já está escrita**, em `ProcessTurn._marcar_falha`
  (`process_turn.py:555`): `turn.fail(...)` → `_gravar` (update + commit) →
  publicar `Failed(reason, delivered_partially)`. São quatro linhas, e a
  varredura precisa exatamente delas.
- **O evento existe** — `Failed` em `application/ports/turn_events.py:101`, com
  `delivered_partially` no payload.
- **`_publicar` engole a falha de propósito** (`process_turn.py:570`) — é a
  única exceção descartada no pipeline inteiro, e o comentário explica por quê.
  A varredura tem o mesmo requisito.
- **`TurnRepository.list_by_session(session_id, *, limit)`** já mostra como o
  repositório faz listagem com `selectinload` (`repositories.py:117`).

### 3.2 O que o card assume e você deve confirmar

| O card diz | Confira |
|---|---|
| *"job periódico do `arq` (`cron_jobs` no `WorkerSettings`)"* | Não há **nenhum** `cron_jobs` no projeto hoje. `WorkerSettings` (`worker/main.py:203`) tem `functions`, `on_startup`, `on_shutdown`, `max_tries`, `max_jobs`. Você vai ser o primeiro |
| *"query nova no `TurnRepository` — provavelmente `list_stale`"* | Não existe. E repare que a listagem precisa dos **trechos** carregados: o `Failed` publica `delivered_partially`, que lê a coleção, e `lazy="raise_on_sql"` estoura se você esquecer o `selectinload` |
| *"prazo folgado em relação ao `teacher_timeout_seconds` × `max_tries`"* | 30 s × 2 (retry do SDK) × 2 (`MAX_TRIES`) — **e a §3.3 pode invalidar o último fator inteiro** |

### 3.3 A investigação que vem ANTES do plano — e pode redesenhar o card

Olhe o caminho de falha real, em `process_turn.py:545-553`:

```python
if turn.audio_chunks or final:
    await self._marcar_falha(turn, str(exc))
    return
logger.warning("turn %s falhou antes do primeiro trecho (%s); devolvendo à fila", ...)
raise exc
```

O `raise` existe para **devolver o job à fila**. Mas lendo o `arq` 0.28
instalado (`.venv/lib/python3.12/site-packages/arq/worker.py`):

- a docstring de `Retry` (linha 97): *"Special exception to retry the job"*;
- no `except` do `run_job` (~613), **só** `Retry`, `CancelledError` e `RetryJob`
  caem no ramo de retry. **Exceção comum cai no `else`**: loga `failed`,
  `finish = True`, `jobs_failed += 1`;
- `max_tries` (549) é usado como **teto** (aborta se `job_try` já passou), não
  como gatilho;
- e `grep -rn "Retry" src` no repositório inteiro **não acha um único `raise`**.

Se isso se confirmar, o `raise exc` acima não devolve nada a lugar nenhum:

1. o turn fica **`processing` para sempre**, sem `failed`, sem evento, com o
   aluno na tela de espera — **exatamente o buraco que este card existe para
   tapar**, só que a causa não é "o worker morreu", é o caminho normal de falha;
2. `MAX_TRIES = 2` limita algo que nunca acontece, e `final_attempt` é sempre
   `False` — então o `ProcessTurn` **nunca** chega no ramo `final`;
3. o prazo da varredura não precisa acomodar duas tentativas.

**Prove primeiro, com execução, não com leitura.** O caminho mais barato é um
teste que enfileira um job cuja função levanta `RuntimeError` e conta quantas
vezes ela foi chamada. Uma ou duas.

**O que fazer com cada resultado:**

- **deu 1** (o retry não existe) → o card ganha um segundo problema, e ele é
  maior que o original. Leve ao desenvolvedor **antes de planejar**: a correção
  pode ser trocar o `raise exc` por `raise Retry(...)`, ou aceitar que não há
  retry e simplificar o `ProcessTurn`. As duas são decisão, e uma delas mexe no
  CARD-026;
- **deu 2** (o retry existe) → o parágrafo acima está errado, o card segue como
  escrito, e a correção vai para o card **com a evidência colada**. Sem drama:
  descobrir que a leitura da biblioteca estava errada é o resultado normal de um
  experimento bem feito.

## 4. As armadilhas

### 4.1 O prazo é a decisão central, e errar para o lado curto custa a fala do aluno

Prazo curto mata turn que estava só demorando; prazo longo mantém o aluno
esperando. A conta precisa estar **escrita**, derivada do pior caso legítimo:

`teacher_timeout_seconds` (30 s) × tentativas do SDK (2) × tentativas do `arq`
(§3.3 decide se é 1 ou 2), mais STT, mais TTS, mais o tempo de fila.

Um turn saudável no p50 leva **2,34 s** (ADR-0047). O pior caso legítimo é uma
ordem de grandeza acima disso. **O prazo não é "um pouco mais que o p50"** — é
"mais que o pior caso que ainda pode dar certo".

### 4.2 A corrida com o worker vivo é real, e o domínio já a resolve

A varredura pode marcar `failed` um turn que o worker está terminando neste
instante. `Turn.fail()` levanta `InvalidStateTransitionError` se o turn já virou
`completed` — então a corrida **não corrompe**, mas ela **quebra o job** se você
não a esperar.

Duas saídas, e a escolha é sua: reler o turn dentro da transação e pular o que
mudou, ou capturar a exceção por item e seguir. A segunda é mais simples e
sobrevive melhor a lote; a primeira é mais explícita. **O que não vale é o job
morrer no meio do lote por causa de um turn.**

### 4.3 `lazy="raise_on_sql"` vai morder aqui

O `Failed` carrega `delivered_partially`, que lê `turn.audio_chunks`. Se a query
de turns travados não fizer `selectinload(TurnRow.audio_chunks)`, o mapeador
**estoura na hora** de publicar. É o comportamento desejado (o CARD-013
demonstrou isso injetando a omissão) — mas só se você souber que vem.

### 4.4 Onde a varredura mora: não duplique `_marcar_falha`

A receita de quatro linhas está dentro de `ProcessTurn`, um caso de uso que
recebe `turn_id` e roda o pipeline inteiro. A varredura precisa da mesma receita
sobre N turns, sem pipeline.

Copiar as quatro linhas é o caminho fácil e o errado: no dia em que a marcação
mudar (um campo novo no evento, um segundo efeito), uma das duas cópias fica
para trás — e é a que ninguém olha. **É um caso de uso novo**, com a marcação
extraída para um lugar só. Onde exatamente é decisão de arquitetura: consulte a
skill `voicecoach-arquitetura`.

### 4.5 O `cron_job` divide o processo com o turno do aluno

`MAX_JOBS = 1` significa **um job por vez** — e o `cron_job` é um job. Enquanto a
varredura roda, nenhum turn é processado. Com lote pequeno é irrelevante; com
500 turns travados e uma transação só, o aluno vivo espera a varredura terminar.

Lote com limite, e o limite é parâmetro. E o card deve **escrever** o que
acontece com duas réplicas de worker: um `cron_job` do `arq` executa em todas.

### 4.6 Publicar para quem já foi embora

O aluno cujo turn travou há dez minutos **não está** com o stream aberto — o SSE
tem timeout de 60 s (`config.py:255`). Publicar o `Failed` mesmo assim está
certo (é barato e cobre quem ainda está lá), mas **não é o mecanismo de
entrega**: quem descobre é o `GET` na volta do app. Não desenhe o card como se o
evento fosse a notificação.

### 4.7 Relógio

Prazo se testa com relógio controlado, nunca com `sleep`. O projeto já injeta o
relógio nos casos de uso (`self._clock()`); siga o padrão em vez de inventar.

## 5. Escopo — o que corta se estourar

- **Não corte:** a §3.3 (ela pode mudar o card); a preservação dos trechos na
  falha; o teste com relógio controlado; a decisão do prazo escrita com a conta.
- **Pode virar card próprio:** o lote e a paginação, se a varredura simples
  resolver; a extração da marcação para um lugar só, **se** a §4.4 revelar que
  ela mexe em mais coisas do que parece.
- **Já está em "Out" e continua:** retentativa automática (ADR-0037); a ação
  manual do aluno (CARD-032); a tela (CARD-027); o encerramento de sessão
  (CARD-034 — mesmo mecanismo, outra entidade, card próprio de propósito).

## 6. Governança

1. **Decisão que os ADRs não cobrem vai ao desenvolvedor ANTES do código:**

   - **D1 — o resultado da §3.3 e o que fazer com ele.** Bloqueia o plano;
   - **D2 — o prazo**, com a conta escrita, não um número redondo;
   - **D3 — onde a marcação de falha passa a morar** (§4.4), já que dois cards
     futuros vão herdar a resposta;
   - **D4 — a corrida do §4.2**: pular ou capturar.

2. **Regra do explicador: no máximo 2, no ponto da decisão, sobre consequência
   observável.** Candidatas boas, porque a resposta se confere rodando:

   - *"um job cuja função levanta `RuntimeError`: quantas vezes o `arq` chama a
     função — uma ou duas? E o que isso significa para o `raise exc` do
     `_tratar_falha`?"* (§3.3 — é o teste que o card precisa de qualquer forma);
   - *"se eu listar turns travados sem `selectinload(audio_chunks)` e publicar o
     `Failed`, o que quebra — e em que linha?"* (§4.3 — demonstração de dois
     minutos, e é a armadilha que o CARD-013 já provou existir).

3. **Item de ADR da DoD** — confira contra `docs/adr/README.md` e **cite o
   critério** (LEARNING-0003). Candidato real: **critério 2**, se a marcação de
   falha mudar de casa (§4.4) — é fronteira entre casos de uso. Se a varredura
   ficar contida, provavelmente **nenhum critério se aplica**, e aí o registro
   por escrito de que nenhum se aplica é o que fecha o item.

4. **A skill `voicecoach-arquitetura` é de consulta obrigatória** — a §4.4 é
   exatamente a pergunta que ela existe para responder.

## 7. Definition of Done específica deste card

Além da DoD do `CLAUDE.md` e dos critérios de aceite do card:

- [ ] **A §3.3 respondida com evidência de execução**, e o `CARD-025` e o
      `card-026-...md` corrigidos para bater com o que a execução mostrou — nos
      dois sentidos.
- [ ] **Um turn travado COM trechos sai `failed` com os trechos intactos** e
      `delivered_partially` verdadeiro. É a invariante do ADR-0023 item 6 e o
      teste tem de olhar a coleção, não só o status.
- [ ] **A corrida testada**: um turn que conclui enquanto a varredura roda não
      derruba o job e não fica com dois estados.
- [ ] **O prazo com a conta escrita** no card — de onde saiu cada fator.
- [ ] **Falha ao publicar não desfaz a marcação** (ADR-0035), com teste.
- [ ] **O que acontece com duas réplicas de worker escrito**, mesmo que hoje
      haja uma só.
- [ ] Card atualizado e `docs/backlog/README.md` atualizado.

## 8. Restrições

- **Branch própria** a partir de `main`. `main` é protegida. **Confira
  `git branch --show-current` depois de criar a branch**: no CARD-011 dois
  commits caíram em `main` apesar de o `git switch -c` ter reportado sucesso.
  Repare que há **dois PRs abertos** (#22 e #23) — se eles ainda não entraram,
  confirme de onde você está partindo.
- Commit **nunca** leva trailer `Co-Authored-By`
  ([LEARNING-0001](../learnings/0001-commit-com-coautoria-indesejada-do-agente.md)).
- **Não pushe nem abra PR sem perguntar.**
- **Custo: US$ 0,00 previstos.** Varredura é testável inteiramente com linhas
  inseridas à mão e relógio fixo — nenhum critério exige chamar provedor. Se
  algo parecer exigir, é o teste que está desenhado errado.
- **Não suba o `MAX_JOBS`** (ADR-0025) e **não reenfileire turn** (ADR-0037).
  Os dois parecem melhorias óbvias enquanto se mexe aqui e não são o escopo.

### Como subir o ambiente inteiro

```bash
docker compose up -d
cd backend && uv run alembic upgrade head
(cd backend && uv run uvicorn voicecoach.api.app:create_app --factory --host 0.0.0.0 --port 8000 &)
(cd backend && uv run voicecoach-worker &)
```

> **Cuidado com processos velhos:** aconteceu no CARD-012, no CARD-013 **e no
> CARD-014** — um uvicorn e um worker de horas antes, servindo código antigo.
> Aqui isso é particularmente traiçoeiro: você vai **matar o worker de
> propósito** para simular turn travado, e um segundo worker vivo que você
> esqueceu vai processar o turn e fazer o teste passar pelo motivo errado.
> `ps aux | grep -E "uvicorn|voicecoach-worker"` antes de começar.

---

- Responda em português. O desenvolvedor é **sênior em C#/.NET** e **iniciante em
  Python**: nada de explicar job periódico ou varredura como conceitos. O que
  interessa é **como o `arq` faz isso e onde a analogia quebra**. Pare para
  explicar em 3 linhas os idiomas sem paralelo — neste card, provavelmente:
  `cron_jobs` como atributo de classe lido por convenção (não há registro no
  contêiner de DI, e a classe **não é instanciada**), e por que um scheduler
  embutido no worker se comporta diferente de um `IHostedService` com
  `PeriodicTimer` quando há mais de uma réplica — o problema que o `Quartz`
  resolve com cluster e o `arq` não resolve sozinho.
