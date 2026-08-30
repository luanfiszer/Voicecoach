# Prompt — CARD-026: a requisição crua deixa de existir, e o retry recém-nascido ganha política

- **Tipo:** prompt de sessão, complemento de `/executa-card 026`
- **Escrito em:** 2026-08-27, na sessão que cruzou o guia arquitetural externo com o backlog
- **Atualizado em:** 2026-08-27, no fim da mesma sessão — o backlog cresceu de
  25 para 36 cards e **três deles passaram a depender da política deste card**
  (§1.1)
- **Atualizado em:** 2026-08-29, depois do CARD-025 — **a §3.3 foi executada e
  respondida**, e a resposta muda cinco seções deste prompt. Leia a §3.3
  primeiro: ela deixou de ser uma investigação e virou um ponto de partida
- **Status:** não executado

> **Este prompt não substitui o `/executa-card`.** Aquele comando carrega o
> protocolo (branch, ordem de leitura, premissas antes do plano, DoD item a
> item, convenção de commit). **Rode `/executa-card 026` e leia isto junto** —
> aqui está a arqueologia já feita, **um achado que já invalidou uma premissa do
> card e foi corrigido por outra sessão** (§3.3), e as armadilhas que custam a
> sessão inteira se descobertas tarde.

> **O que mudou desde a última revisão deste prompt.** A §3.3 previa uma
> investigação; ela foi executada no **CARD-025** (2026-08-29, PR #24) e o `arq`
> **não** retenta exceção comum — deu **1 chamada**, não 2. Aquela sessão
> corrigiu o buraco, então **o retry deste projeto passou a existir de verdade**,
> e este card herda um mecanismo real em vez de um diagnóstico errado. As
> consequências estão marcadas com **[atualizado 2026-08-29]** ao longo do texto,
> e a decisão está no
> [ADR-0052](../adr/0052-o-retry-do-arq-e-explicito-e-a-marcacao-de-falha-mora-num-lugar-so.md).

---

## 0. Antes do plano: a fila de perguntas

**[atualizado 2026-08-29]** Última sessão executada: **CARD-025** (PR #24). A
pergunta dela foi feita no ponto da decisão e **dispensada pelo desenvolvedor**
(*"esquece explicador"*) — dispensa **não** volta na abertura seguinte: ela tem
desfecho, e o desfecho é a dispensa (CLAUDE.md, regra do explicador, item 3).

Logo, **a fila está vazia** e você não reapresenta nada. Vale saber, porém, que a
pergunta dispensada era exatamente a **candidata nº 1 da §6 deste prompt** — o
que a tira da lista aqui também: o experimento foi feito, e o resultado está
preso em `tests/worker/test_varredura_e_retry.py`.

O CARD-015 **não foi executado**; o prompt dele existe e continua válido, só
mudou de posição na fila (este card entrou na frente — o motivo está no
`docs/backlog/README.md`).

**Não reapresente Q7/Q13/Q14.** Estão arquivadas e só voltam quando um card tocar
a decisão delas, refeitas no ponto da decisão daquele card. Este card não toca
nenhuma.

O que esta sessão produz são **perguntas novas**, no máximo duas, no ponto da
decisão. Candidatas na §6.

---

## 1. Por que este card, e por que antes do CARD-015

Origem: guia arquitetural externo (aula de arquitetura .NET, §01), trazido pelo
desenvolvedor. **O guia não é autoridade neste repositório** — os ADRs são. Ele
entrou porque apontou um buraco que se confirmou no código, com número.

Duas coisas que você não deve confundir:

| | Protege contra | Card |
|---|---|---|
| Cota, kill switch, rate limit | **o cliente** — o aluno que gasta demais | CARD-015 |
| Timeout, retry, breaker, bulkhead | **a dependência** — o provedor que cai ou fica lento | **este** |

Calibrar limite de uso sobre uma fronteira que ainda pode pendurar 60 s é
calibrar sobre areia. Daí a ordem.

**O que o guia acrescenta e o projeto não tinha:** a regra de que a política de
resiliência é decidida **no refinamento**, não no fim. Ela já entrou no
`docs/backlog/CARD-000-template.md` (seção "Refinamento obrigatório") na mesma
sessão que escreveu este card — a partir de agora todo card com dependência
externa responde as mesmas quatro perguntas.

### 1.1 O que mudou depois que este prompt foi escrito — e por que aumenta o peso do card

A mesma sessão varreu o `Design.pdf` e criou dez cards a mais. **Três deles
consomem o que você decidir aqui**, e isso desloca duas decisões da §6 de
"escolha local" para "contrato que outros cards herdam":

| Card novo | O que ele espera deste |
|---|---|
| **CARD-027** (telas de exceção) | é a **tela** do desfecho "provedor indisponível". O que você decidir na **D4** é literalmente o que o aluno vai ler |
| **CARD-033** (saldo de cota e serviço pausado) | precisa distinguir *"o produto pausou por orçamento"* de *"a dependência caiu"*. São duas indisponibilidades diferentes e a tela é outra |
| **CARD-036** (tradução sob demanda) | é a **segunda** chamada externa do produto, e o card dele já diz que nasce com a política deste — não com requisição crua |

Consequência prática para o plano: **a D2 (biblioteca ou código próprio) deixa
de ser sobre este card.** Se for código próprio, ele será reusado pelo adapter
de tradução — o que é argumento a favor de escrevê-lo bem e contra escrevê-lo
"só o suficiente para o S3". E a **D4 vira decisão de produto**, não de
infraestrutura: quem a responde é o desenvolvedor, e ela tem tela.

**[atualizado 2026-08-29] O que mudou de novo, e a favor deste card:** o
**CARD-025 rodou** e a §3.3 foi respondida. As duas consequências para você:

1. **a rede de segurança existe.** A varredura encerra qualquer turn parado além
   de `stale_turn_after` (5 min). Durante esta sessão você **vai** fazer turns
   falharem de formas novas — e agora dá para distinguir "o meu timeout mordeu"
   de "travou e ninguém percebeu", que é a diferença entre ver a falha e olhar
   uma tela de espera sem saber se o bug é seu;
2. **o retry existe.** Não é mais um `MAX_TRIES` decorativo: o `ProcessTurn`
   levanta `RetryableTurnFailureError` e `worker/main.py` traduz em
   `arq.Retry(defer=0)`. **O `defer=0` é provisório e é seu** — ver §3.3.

## 2. O que já está decidido e não se rediscute

- [**ADR-0030**](../adr/0030-saida-estruturada-em-streaming-por-tool-use-com-deltas-granulares.md)
  e [**ADR-0037**](../adr/0037-a-cascata-e-uma-fila-interna-com-um-consumidor-so.md) —
  **nada de retry depois do primeiro trecho entregue.** O aluno já ouviu; refazer
  faria a resposta recomeçar do zero. Isto não está em disputa e limita o desenho
  inteiro: a janela onde retry é legítimo é **antes do primeiro `yield`**, e o
  `anthropic_teacher.py:358` já documenta que a conexão só abre no `__aenter__`.
- [**ADR-0034**](../adr/0034-adapter-s3-sincrono-em-executor-e-retencao-por-tag.md)
  — o adapter de S3 é **síncrono num executor**, de propósito (o `boto3` não tem
  versão async). O card **não** troca por `aioboto3`; ele configura o que já
  existe. Trocar de SDK é outro ADR e outro card.
- [**ADR-0012**](../adr/0012-regra-de-camada-como-contrato-executavel.md) —
  resiliência é **detalhe de infraestrutura**. `domain` e `application` não podem
  saber que existe circuito aberto, backoff ou pool de threads. Se a política
  vazar para a porta, o desenho está errado. O `lint-imports` vai avisar se você
  importar a biblioteca no lugar errado; ele **não** avisa se você inventar um
  conceito de resiliência dentro do caso de uso.
- [**ADR-0025**](../adr/0025-modelos-residentes-no-worker-e-readiness-que-distingue-pronto.md)
  — `MAX_JOBS = 1` **não é limitação técnica**: STT e TTS disputam a mesma CPU e
  dois turns concorrentes se atrasariam mutuamente. Não suba isso "para
  paralelizar" enquanto mexe em pools; o gatilho está escrito no
  `worker/main.py:73-77` e é medição de CPU ociosa com fila cheia.
- **[novo 2026-08-29]** [**ADR-0052**](../adr/0052-o-retry-do-arq-e-explicito-e-a-marcacao-de-falha-mora-num-lugar-so.md)
  — **pedir retentativa é um tipo, e a tradução para o `arq` mora na composition
  root.** `application` não importa `arq`: o caso de uso levanta
  `RetryableTurnFailureError` e quem monta o `arq.Retry` é `worker/main.py`.
  Qualquer política de retry que você desenhar **respeita essa fronteira** — uma
  biblioteca de retry decorando um caso de uso é seta proibida, mesmo que o
  `lint-imports` não a pegue (ela pega o import, não o conceito).
- [**ADR-0047**](../adr/0047-fila-de-playback-com-um-player-por-trecho-e-a-rota-de-medicao.md)
  — o p50 medido é **2,34 s** (CARD-013). É o orçamento contra o qual todo
  timeout deste card se justifica. Número que não se derive dele é chute.
- [**ADR-0039**](../adr/0039-result-minimo-para-desfecho-esperado-de-caso-de-uso.md)
  / [**0040**](../adr/0040-formato-de-erro-da-api-problem-details.md) — se
  "provedor indisponível" virar desfecho visível na API, é `Err` + Problem
  Details, nunca exceção vazando nem `JSONResponse` na rota.

## 3. Arqueologia — verificada no repositório em 2026-08-27

### 3.1 O que já existe e você não constrói de novo

- **Tradução de erro na fronteira, nos três adapters.** `MediaStorageError`
  (`s3_media_storage.py`, nos dois `_in_executor`), `SttError`, e a lista
  `FALHAS_DE_INFRAESTRUTURA` em `process_turn.py:109-112`. O `botocore` **não**
  vaza para `application` — isso é ACL do guia §02, já feito. Sua política nova
  se pendura aqui, não num lugar novo.
- **Timeout do professor configurável** — `teacher_timeout_seconds` (default
  30 s), com o comentário em `config.py:184-188` já explicando que é timeout de
  **uma tentativa** e que o SDK multiplica por até 3.
- **Teto de concorrência da fila** — `MAX_JOBS = 1`.
- **O caminho triste já existe e é fino** — `process_turn.py` distingue falha
  antes e depois do primeiro trecho, e `Turn.fail(motivo, now)` aceita a partir
  de `queued` **e** de `processing`. Você acrescenta um motivo novo; não
  redesenha o ciclo de vida.
- **[novo 2026-08-29] A marcação de falha tem um dono só** — `FailTurn`, em
  `application/use_cases/fail_turn.py`, com a receita `fail()` → gravar →
  publicar e a política `publicar_tolerante`. Se este card criar um desfecho novo
  ("provedor indisponível"), ele passa por **ali**, não por uma quarta cópia das
  mesmas quatro linhas.
- **[novo 2026-08-29] O retry, de ponta a ponta.**
  `RetryableTurnFailureError` (`process_turn.py`) → `except` em
  `worker/main.py` → `raise Retry(defer=0)`. **É o único ponto do projeto que
  pede reexecução**, e é onde o backoff deste card entra.
- **[novo 2026-08-29] Há um `cron_jobs` no `WorkerSettings`** — a varredura do
  CARD-025, a cada minuto. Se você criar um segundo job periódico (não deveria
  neste card), o padrão já existe.

### 3.2 O que o card assume e você deve confirmar antes de planejar

| O card diz | Confirme assim |
|---|---|
| *"defaults do botocore: 60 s connect, 60 s read, 5 tentativas"* | Não confie no prompt. `python -c "from botocore.config import Config; print(Config().connect_timeout, Config().read_timeout, Config().retries)"` no venv do projeto, e cole o resultado no card |
| *"quatro adapters dividem o mesmo pool"* | `grep -rn "run_in_executor(None" src` — são STT, TTS, encoding e storage. O tamanho do pool default é `min(32, os.cpu_count() + 4)`; imprima o número da máquina onde você vai medir |
| *"120 s por turn com o provedor morto"* | **[atualizado 2026-08-29]** A §3.3 respondeu: hoje o número é verdadeiro, porque o retry do `arq` passou a existir. Continua valendo **medir, não multiplicar** — três camadas em série não somam de forma óbvia (§4.6) |

### 3.3 [RESOLVIDO em 2026-08-29] O achado se confirmou, e o CARD-025 o corrigiu

**Esta seção era uma investigação bloqueante. Não é mais — não refaça o
experimento, leia o resultado e siga.**

A leitura do `arq` 0.28 estava certa, e foi medida com worker e Redis reais
(`tests/worker/test_varredura_e_retry.py`):

| Exceção levantada pela task | Chamadas da função | `jobs_retried` |
|---|---|---|
| `RuntimeError` (exceção comum) | **1** | 0 |
| `arq.Retry(defer=0)` | **2** (`job_try` 1, depois 2) | 2 |

No `run_job`, só `Retry`, `CancelledError` e `RetryJob` caem no ramo de retry;
o resto cai no `else`, que loga `failed` e encerra. `max_tries` é **teto**, não
gatilho. Confirmado: o `MAX_TRIES = 2` limitava um contador que nunca passava de
1, `final_attempt` era sempre `False`, e o turn ficava `processing` para sempre.

**O CARD-025 corrigiu isso** (ADR-0052): o caso de uso levanta
`RetryableTurnFailureError`, e `worker/main.py` traduz em `arq.Retry(defer=0)`.

#### O que isso muda para ESTE card — três coisas, e a terceira é sua

**1. O item 3 do card estava errado no diagnóstico, e agora está certo.** Ele
dizia *"cada turn paga `teacher_timeout_seconds` × 2 tentativas do SDK ×
`MAX_TRIES = 2` — até ~120 s"*. Até 2026-08-29 isso era falso (o fator do `arq`
não existia: o real eram ~60 s). **Com o retry funcionando, os ~120 s passaram a
ser verdade** — e o `defer=0` os torna consecutivos, sem espera entre as
tentativas. O card já foi corrigido; o argumento a favor do breaker ficou **mais**
forte, não menos.

**2. O orçamento de tempo do turno agora tem três camadas de retry, não duas.**
Isto é o que a §4.6 dizia com duas, e é a conta que você precisa fechar:

```
teacher_timeout_seconds (30 s)
  × retry do SDK da Anthropic (max_retries=2, default)
  × retry do arq (MAX_TRIES = 2, agora REAL)
  [ × o retry que este card talvez acrescente ]
```

Empilhar uma quarta camada sem desligar alguma é multiplicar tempo de parede por
um fator que ninguém escreveu em lugar nenhum. **Decida quais camadas retentam e
desligue as outras explicitamente.**

**3. O `defer=0` é dívida declarada do CARD-025, e ela é deste card.** Está
escrito no comentário do `worker/main.py`: *"o backoff que interessa já aconteceu
dentro do adapter do professor; somar outro aqui só aumentaria o tempo em que o
aluno olha uma tela sem saber de nada"*. Isso foi a escolha certa **enquanto não
havia política nenhuma**. Este card é o lugar onde `defer` deixa de ser 0 — ou
onde se decide, por escrito, que ele continua 0 porque o backoff mora numa
camada de dentro. As duas respostas servem; o que não serve é não perceber que a
pergunta existe.

#### O que NÃO refazer

O experimento está preso em teste, contra um `arq` real, com a variante que dá 2.
Se a biblioteca mudar de comportamento, ele aponta. **Não gaste sessão
reconfirmando o que já tem regressão.**

## 4. As armadilhas

### 4.1 Configurar timeout sem configurar `retries` multiplica o timeout por 5

No `botocore`, `connect_timeout`/`read_timeout` são **por tentativa**. O modo de
retry default (`legacy`) tenta até 5 vezes. Um `read_timeout=2` sem tocar em
`retries` não dá 2 s de teto: dá até 10 s, mais o backoff interno. Os três
parâmetros vão juntos ou não vão:

```python
Config(
    signature_version="s3v4",   # já existe e é obrigatório (MinIO só aceita v4)
    connect_timeout=...,
    read_timeout=...,
    retries={"max_attempts": ..., "mode": "standard"},
)
```

O `mode="standard"` importa: o `legacy` tem uma lista de erros retryable
diferente e não respeita `max_attempts` da mesma forma. **Escreva no card qual
modo você escolheu e por quê** — é decisão, não default.

### 4.2 O timeout do storage tem um piso que não é o orçamento do turno

Tentador derivar o timeout do S3 de "2,4 s de orçamento, logo 500 ms". Não é
assim: o `put_object` de um trecho carrega **áudio**, e o tempo depende do
tamanho do trecho e da banda. Um timeout abaixo do tempo de upload real
transforma turno saudável em falha — que é o risco central do card e o mesmo do
CARD-025.

**[novo 2026-08-29] E o CARD-025 já deixou o formato da resposta pronto — com um
erro dentro dele que vale mais que o formato.** O `stale_turn_after` não é um
número redondo: é uma conta no `config.py`, parcela a parcela, cada uma com a
medição de origem. **Copie o formato**, não o número.

O erro: a primeira versão daquela conta dizia *"sem fator de retentativa do
`arq`"* — verdade sobre o código de antes da sessão, e falsa sobre o código que a
**mesma sessão** produziu, porque foi ela que fez o retry existir. Corrigido no
mesmo dia (pior caso ~146 s em vez de 77 s; a folga caiu de ~3,9× para ~2,05×).
**É o modo de falha de toda conta escrita no meio de uma mudança: ela descreve o
sistema de ontem com a autoridade de um número medido.** Você vai escrever várias
neste card, e todas sob mudança.

Os dois números também são **acoplados**, nos dois sentidos: se o seu timeout
encurtar o pior caso legítimo, o prazo de 5 min ganha folga demais e pode cair;
se você puser backoff no `defer` do `arq.Retry`, o pior caso cresce e **o prazo
tem de subir junto**. O gatilho está escrito no `config.py`; fechá-lo é deste
card.

Meça antes de escolher: quanto tempo o `put_object` de um trecho típico leva
hoje, contra o MinIO local **e** com um trecho grande. O número vai para o card.
E lembre que o `_in_executor` inclui a espera por **thread livre**, não só a
chamada — o que liga esta armadilha à §4.3.

### 4.3 Executor separado é fácil de criar e fácil de vazar

Trocar `run_in_executor(None, ...)` por um `ThreadPoolExecutor` próprio é uma
linha. O que não é uma linha:

- **quem fecha.** Um executor sem `shutdown()` mantém threads vivas e o processo
  não termina. O ciclo de vida tem dono: `lifespan` na API
  (`api/lifespan.py`), `on_startup`/`on_shutdown` no worker
  (`worker/main.py`) — é onde `app.state.redis` e os modelos residentes já
  moram. Não crie executor no construtor do adapter sem dizer quem o fecha.
- **quem os recebe.** O adapter não pode ir buscar um executor global; ele
  recebe no construtor, montado no composition root, como todo o resto
  (`create_media_storage`, `create_teacher_llm`).
- **o teste.** Um pool que vaza aparece como teste que trava no fim da suíte, não
  como falha. Se a suíte começar a demorar para encerrar, é aqui.

**Idioma sem paralelo direto em C#:** `run_in_executor(None, ...)` usa *um* pool
default por event loop — não é o `ThreadPool` do .NET com work-stealing e
crescimento dinâmico. É um `ThreadPoolExecutor` de tamanho fixo
(`min(32, cpu+4)`), e passar `None` significa literalmente *o mesmo pool para
todo mundo*. Explique isso em 3 linhas quando chegar a hora, não antes.

### 4.4 Circuit breaker com estado em processo não é global — e aqui isso é OK

Dois processos (API e worker) e, um dia, duas réplicas de worker: cada um abre o
próprio circuito. **Isso é aceitável e deve estar escrito**, com o que mudaria se
importasse (estado no Redis, que já está aberto no `lifespan` e já é o "caminho
rápido" do ADR-0035). O que não é aceitável é o card fingir que o estado é
compartilhado.

Repare também que hoje o professor só é chamado **do worker**, com `MAX_JOBS = 1`
— ou seja, uma chamada por vez. Um breaker aqui não protege contra concorrência;
protege contra **repetição em série**. É um argumento a favor de um breaker
simples e contra uma biblioteca grande.

**[novo 2026-08-29] Há um precedente de coordenação entre réplicas no projeto, e
ele não é um lock.** O CARD-025 descobriu que o `cron_jobs` do `arq` coordena N
réplicas **pela unicidade da chave**: `unique=True` monta um `job_id`
determinístico (`f'{name}:{to_unix_ms(next_run)}'`) e o segundo `enqueue_job` é
recusado pelo Redis — medido, 1 job com o default e 2 com `unique=False`. Se o
estado do breaker um dia precisar ser compartilhado, **é este o vocabulário a
imitar** (uma chave no Redis com significado), e não um lock distribuído. Não
implemente isso agora; saiba que o caminho já tem precedente escrito.

### 4.5 Dependência nova por ~40 linhas de código

`tenacity` (retry declarativo por decorator) é a escolha óbvia e resolve metade
do card; a outra metade (breaker) não tem opção async óbvia e madura no
ecossistema. O ADR precisa defender nos **dois** sentidos: o que a biblioteca
custa (uma dependência para sempre, ADR-0038 mostrou o que uma delas fez com a
versão do `redis`) contra o que ela substitui. **Escrever 40 linhas testadas é
uma resposta legítima** neste card; escrevê-las sem considerar a alternativa não
é.

Se `tenacity` entrar: confirme que ela não rebaixa nada, com dry-run, como o
CARD-010 fez.

### 4.6 [atualizado 2026-08-29] Agora são TRÊS camadas de retry, não duas

`AsyncAnthropic(api_key=...)` (em `adapters/llm/factory.py`) usa `max_retries=2`
por default. Empilhar `tenacity` por cima sem zerar o do SDK multiplica as
tentativas e o tempo de parede.

**E desde o CARD-025 existe uma terceira**, que antes era decorativa e agora
morde: o `arq.Retry(defer=0)` que `worker/main.py` levanta a partir do
`RetryableTurnFailureError`. Ela é a mais externa das três — reexecuta a **task
inteira**, do `turns.get()` em diante.

| Camada | Onde | O que reexecuta | Ligada hoje |
|---|---|---|---|
| SDK da Anthropic | `llm/factory.py` | a requisição HTTP | sim (`max_retries=2`, default) |
| a que este card talvez acrescente | adapters | a chamada ao provedor | — |
| `arq` | `worker/main.py` | **o turn inteiro** (só antes do 1º trecho) | **sim, desde 2026-08-29** |

**Decida qual retenta e desligue as outras explicitamente** — e escreva a
decisão, porque as três são invisíveis no código de quem lê depois. A de fora
tem uma propriedade que as outras não têm: ela é a única que sobrevive ao
processo morrer no meio.

### 4.7 Testar "lento" e "morto" não é a mesma coisa, e nenhum dos dois é "erro"

Três cenários, três testes, e é fácil escrever só o terceiro:

- **lento** — responde, mas depois do timeout. Precisa de um fake que durma;
- **morto** — a conexão nem abre (porta fechada). `ClientError` e `BotoCoreError`
  chegam por caminhos diferentes;
- **com erro** — responde rápido, com falha de negócio. **Não deve abrir o
  circuito** — um `NoSuchKey` não é o provedor caindo.

O terceiro é o que separa um breaker útil de um que abre sozinho em produção.

## 5. Escopo — o que corta se estourar

- **Não corte:** timeout explícito nos três adapters (é o item com risco medido);
  **a conta das três camadas de retry** (§4.6) e o desfecho do `defer` (§3.3, item
  3); o teste de dependência lenta com tempo medido.
- **Pode virar card próprio:** o executor separado (§4.3), se a medição mostrar
  que com `MAX_JOBS = 1` o ganho é teórico — mas então **escreva o gatilho**, do
  jeito que o `MAX_JOBS` fez; o breaker, se a medição mostrar que o retry corrigido
  pelo CARD-025 mais o timeout já resolvem o caso que importa.
- **Escreva pensando no segundo consumidor.** O CARD-036 vai pendurar um adapter
  de tradução na mesma política. Não generalize por antecipação — mas se a
  escolha for código próprio, ele mora onde um segundo adapter consiga usá-lo,
  e não dentro do `s3_media_storage.py`.
- **Já está em "Out" e continua:** rate limit e cota (CARD-015); observabilidade
  das aberturas de circuito. A **varredura de travados saiu de "Out" por outro
  motivo**: ela foi feita (CARD-025) e agora é infraestrutura de que você se
  beneficia, não escopo que você evita.

## 6. Governança

1. **Decisão que os ADRs não cobrem vai ao desenvolvedor ANTES da primeira linha
   de código.** Nesta sessão, no mínimo:

   - **D1 [atualizado 2026-08-29] — a conta das três camadas de retry** (§4.6):
     quais retentam, quais são desligadas, e qual o tempo de parede máximo que
     sobra. **Bloqueia o plano**, porque todo timeout que você escolher depois
     depende dessa conta. Não é mais uma investigação — é uma decisão sobre um
     mecanismo que já existe;
   - **D5 [novo 2026-08-29] — o `defer` do `arq.Retry`**: continua 0, ou vira
     backoff? É dívida declarada do CARD-025 e o card dela aponta para cá. A
     resposta "continua 0, porque o backoff mora numa camada de dentro" é
     legítima — desde que escrita;
   - **D2 — biblioteca ou código próprio** para retry e breaker (§4.5), com o
     dry-run de rebaixamento na mão;
   - **D3 — os números**: timeout de cada adapter, N falhas para abrir o
     circuito, janela de recuperação. Cada um derivado de medição, não de gosto;
   - **D4 — o que o aluno vê** quando o provedor está fora. Motivo novo no
     `Turn.fail`? Desfecho novo no `Result` (e aí a rota e o `assert_never` vão
     junto — o mecanismo do ADR-0039 cobrando exaustividade)? Ou nada visível e
     só log? **Esta virou decisão de produto** (§1.1): o CARD-027 desenha a tela
     em cima dela, e o CARD-033 precisa que ela seja distinguível de "o produto
     pausou por orçamento".

2. **Regra do explicador: no máximo 2, no ponto da decisão, sobre consequência
   observável.** Candidatas boas, porque a resposta se confere rodando:

   **[atualizado 2026-08-29] A candidata nº 1 original saiu**: ela era a pergunta
   da §3.3, que já foi feita (e dispensada) no CARD-025, com o resultado preso em
   teste. Repeti-la seria cobrar de novo uma pergunta já arquivada com evidência,
   que é exatamente o defeito que o LEARNING-0005 corrigiu. As duas candidatas
   agora são:

   - *"com `read_timeout=2` e `retries` não configurado, quanto tempo de parede
     leva um `put_object` contra uma porta que engole pacotes — 2 s ou mais? Por
     quê?"* (§4.1 — demonstração de poucos minutos que mata a dúvida de vez);
   - *"o `AsyncAnthropic` com `max_retries=2` e um `tenacity` de 3 tentativas por
     cima: com o provedor morto, quantas requisições HTTP saem — 3, 5 ou 6? E
     quantas vezes a task inteira roda, considerando o `arq.Retry`?"* (§4.6 — a
     conta das três camadas, conferível contando chamadas num fake, e é a
     pergunta cujo erro custa mais caro nesta sessão).

3. **Item de ADR da DoD** — confira contra `docs/adr/README.md` e **cite o
   critério** (LEARNING-0003). Visíveis: **critério 1** se entrar biblioteca;
   **critério 2** (comportamento da fronteira porta/adapter muda para todo
   consumidor); **critério 5** (timeout mal calibrado só aparece em produção, e
   reverter exige recalibrar tudo).

4. **A skill `voicecoach-arquitetura` é de consulta obrigatória** — card de
   backend, e a pergunta "onde mora a política de resiliência" é exatamente o
   tipo de coisa que ela existe para responder.

## 7. Definition of Done específica deste card

Além da DoD do `CLAUDE.md` e dos critérios de aceite do card:

- [ ] **[atualizado 2026-08-29] A conta das três camadas de retry escrita**
      (§4.6), com o tempo de parede máximo medido — não multiplicado no papel — e
      a decisão de qual camada retenta.
- [ ] **O desfecho do `defer=0` registrado** (§3.3, item 3): virou backoff, ou
      continua 0 com o motivo escrito. Dívida do CARD-025 que este card fecha.
- [ ] **Nenhum timeout herdado de default de biblioteca** em caminho de rede.
      Cada número tem uma linha dizendo de onde saiu.
- [ ] **Os três cenários da §4.7 testados** — lento, morto e com erro —, e o
      terceiro provando que o circuito **não** abre.
- [ ] **Tempo de parede medido**, não estimado, no cenário "storage não
      responde": o teste mede e afirma o teto.
- [ ] **Se houver executor próprio:** existe teste de que ele fecha, e a suíte
      continua encerrando no mesmo tempo.
- [ ] **A limitação do breaker por processo escrita** (§4.4), com o gatilho para
      mudar.
- [ ] **`domain` e `application` sem uma linha nova sobre resiliência** —
      `lint-imports` verde não basta, olhe o diff.
- [ ] Card atualizado e `docs/backlog/README.md` atualizado.

## 8. Restrições

- **Branch própria** a partir de `main`. `main` é protegida. **Confira
  `git branch --show-current` depois de criar a branch**: no CARD-011 dois
  commits caíram em `main` apesar de o `git switch -c` ter reportado sucesso.
- Commit **nunca** leva trailer `Co-Authored-By`
  ([LEARNING-0001](../learnings/0001-commit-com-coautoria-indesejada-do-agente.md)).
- **Não pushe nem abra PR sem perguntar.**
- **Custo: US$ 0,00 previstos.** Timeout, retry e breaker são testáveis
  inteiramente com fakes e com o MinIO local — nenhum critério exige chamar a
  Anthropic. Se algo parecer exigir, é o teste que está desenhado errado.
  Para simular "morto", uma porta fechada basta; para "lento", um fake que dorme.
- **Não troque o `boto3` por `aioboto3`** (ADR-0034) nem suba o `MAX_JOBS`
  (ADR-0025). Os dois parecem melhorias óbvias enquanto se mexe em pool e não
  são o escopo.
- **Não antecipe observabilidade.** A vontade de instrumentar aberturas de
  circuito com OpenTelemetry vai aparecer; não há telemetria no projeto e este
  card não a introduz.

### Como subir o ambiente inteiro

```bash
docker compose up -d
cd backend && uv run alembic upgrade head
(cd backend && uv run uvicorn voicecoach.api.app:create_app --factory --host 0.0.0.0 --port 8000 &)
(cd backend && uv run voicecoach-worker &)
```

> **Cuidado com processos velhos:** aconteceu no CARD-012, no CARD-013, no
> CARD-014 **e de novo no CARD-025** (um uvicorn de horas antes, ainda de pé).
> Neste card isso é pior que de costume: você vai **medir tempo**, e um processo
> velho sem a configuração nova produz um número que parece bom e não significa
> nada. `ps aux | grep -E "uvicorn|voicecoach-worker"` antes de medir qualquer
> coisa, e derrube o que você subiu ao terminar.
>
> **[novo 2026-08-29] O worker agora varre a cada minuto.** Se você deixar um
> turn parado enquanto mexe em timeout, ele vira `failed` sozinho depois de
> `stale_turn_after` (5 min). Isso é a rede de segurança funcionando — mas num
> teste manual de tempo é uma variável a mais. Ou meça dentro da janela, ou suba
> o prazo por env (`STALE_TURN_AFTER`) enquanto mede, e **volte ao default**.

---

- Responda em português. O desenvolvedor é **sênior em C#/.NET** e **iniciante em
  Python**: nada de explicar circuit breaker, bulkhead ou backoff como conceitos
  — ele os conhece do Polly. O que interessa é **como Python faz isso e onde a
  analogia com o Polly quebra**. Pare para explicar em 3 linhas os idiomas sem
  paralelo — neste card, provavelmente: o `ThreadPoolExecutor` fixo por trás do
  `run_in_executor` (§4.3), o retry por **decorator** em vez de pipeline de
  handlers registrado no contêiner de DI (não existe `HttpClientFactory` aqui), e
  a diferença entre configurar timeout no cliente do SDK e envolvê-lo num
  `asyncio.timeout` — que não são a mesma coisa e falham diferente.
- **[novo 2026-08-29]** Se o retry por decorator entrar, vale um parágrafo sobre
  por que ele **não** pode decorar um caso de uso: em C# a política de resiliência
  é registrada no contêiner e aplicada por `HttpClientFactory`, longe do código de
  negócio quase por acidente do framework. Em Python um decorator é só uma função
  que embrulha outra — nada impede que alguém o ponha no lugar errado, e o
  `lint-imports` pega o **import**, não o conceito (ADR-0012, ADR-0052).
