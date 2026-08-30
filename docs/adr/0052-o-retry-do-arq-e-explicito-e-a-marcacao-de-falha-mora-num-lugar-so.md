# ADR-0052 — O retry do `arq` é explícito, e a marcação de falha mora num lugar só

- **Status:** aceito
- **Data:** 2026-08-29
- **Critério de obrigatoriedade** (`docs/adr/README.md`): **critério 2 — define
  ou altera uma fronteira.** São duas: a marcação de falha deixa de ser um método
  privado do `ProcessTurn` e passa a ser um colaborador compartilhado de
  `application`, e nasce um **tipo de contrato entre `application` e o worker**
  (`RetryableTurnFailureError`) que traduz "quero outra tentativa" sem que o
  núcleo conheça o `arq`.

## Contexto

O CARD-025 existia para dar dono ao turn que ninguém termina: um `queued` cujo
worker nunca apareceu, ou um `processing` cujo worker morreu, ficava assim para
sempre, com o aluno numa tela de espera que nada encerrava.

A investigação que precedeu o plano encontrou um segundo buraco, **maior que o
original e pelo mesmo sintoma**. O `ProcessTurnHandler._tratar_falha` levantava
a exceção de infraestrutura crua quando o turn falhava antes do primeiro trecho,
com o comentário *"devolvendo à fila"*. Medido contra o `arq` 0.28 instalado:

| Exceção levantada pela task | Chamadas da função | `jobs_retried` |
|---|---|---|
| `RuntimeError` (exceção comum) | **1** | 0 |
| `arq.Retry(defer=0)` | **2** (`job_try` 1, depois 2) | 2 |

No `arq.worker.Worker.run_job`, só `Retry`, `CancelledError` e `RetryJob` caem no
ramo de retry; qualquer outra exceção cai no `else`, que loga `failed` e encerra
o job. E `max_tries` é usado como **teto** (aborta se `job_try` já passou), não
como gatilho. Consequências no código como ele estava:

1. o turn ficava `processing` para sempre — **o buraco do card, chegando pelo
   caminho normal de falha**, não por worker morto;
2. `MAX_TRIES = 2` limitava um contador que nunca passava de 1;
3. `final_attempt` era sempre `False`, então o ramo `final` de `_tratar_falha`
   era código morto — e o teste que o cobria passava porque o teste o forçava.

Ao mesmo tempo, a varredura precisava da receita de marcação (`fail()` → gravar →
publicar `Failed`) que vivia dentro do `ProcessTurn`, sobre N turns e sem
pipeline. Duas cópias de quatro linhas que ninguém veria divergir.

## Decisão

**1. Pedir retentativa é um tipo, e a tradução para `arq.Retry` mora na
composition root.** O caso de uso levanta `RetryableTurnFailureError`
(encadeando a causa original com `raise ... from exc`); a task
`worker.main.process_turn` a captura e levanta `arq.Retry(defer=0)`.
`application` continua sem importar `arq` (ADR-0012), e `MAX_TRIES` passa a
significar o que o comentário dele sempre disse.

**2. A marcação de falha mora em `application/use_cases/fail_turn.py`**, como o
colaborador `FailTurn` (e a política `publicar_tolerante`, que engole falha de
canal — ADR-0035). `ProcessTurn` e `SweepStaleTurns` usam o mesmo objeto. Não é
um caso de uso: não tem comando próprio porque não é uma intenção do sistema, é
um passo dentro de duas.

**3. A varredura é `SweepStaleTurns`, um caso de uso disparado por um
`cron_job`**, com prazo e lote vindos da config por parâmetro (ADR-0013). Ela
**marca falho e não retenta** (ADR-0037).

**4. A listagem devolve ids, não entidades.** `TurnRepository.list_stale(before,
limit) -> list[UUID]`, e quem varre relê cada turn pelo `get` antes de encerrá-lo.
Uma lista de `Turn` seria uma foto: entre o SELECT e o `update`, o worker pode ter
concluído o turn, e gravar a foto escreveria `failed` sobre `completed` — sem que
a proteção de `Turn.fail()` disparasse, porque a entidade em memória ainda diria
`processing`. Com o objeto fresco, quem recusa é o domínio, e a
`InvalidStateTransitionError` é capturada **por item**, para que um turn não
derrube o lote. Um commit por turn, não um por rodada.

**5. O prazo é `stale_turn_after = 5 min`, derivado do pior caso legítimo**, com
a conta escrita no `config.py`. Ela tem duas parcelas, e a segunda é consequência
da decisão 1 desta mesma ADR: o pipeline sem retry são 77 s (STT 8 + professor 60
+ TTS 4 + IO 5), mas como o retry **passou a existir**, o pedaço até o primeiro
trecho (~69 s) dobra — a guarda do `ProcessTurn` só retenta antes dele
(ADR-0037). Pior caso ≈ **146 s**, e os 300 s são ~2,05× isso.

> **Erro corrigido no mesmo dia, e vale registrar por quê.** A primeira versão
> desta conta dizia "sem fator de retentativa do `arq` — é o que a medição
> removeu". Era verdade sobre o código **antes** da decisão 1, e falsa sobre o
> código que esta mesma ADR produziu. A medição removeu o fator; a correção o
> devolveu. É o modo de falha clássico de uma conta escrita no meio de uma
> mudança: ela descreve o sistema de ontem com a autoridade de um número medido.

## O que a medição corrigiu no card, e no sentido contrário

O CARD-025 afirmava que *"um `cron_job` do arq com mais de uma réplica de worker
executa em todas"* — e usava isso como objetivo de aprendizado (*"o problema que
o Quartz resolve com cluster e o arq não resolve sozinho"*). **É falso com o
default.** Em `arq.worker.run_cron`:

```python
job_id = f'{cron_job.name}:{to_unix_ms(cron_job.next_run)}' if cron_job.unique else None
```

`unique=True` é o default de `arq.cron`. As réplicas calculam o mesmo `next_run`,
montam o mesmo `job_id`, e o `enqueue_job` da segunda é recusado. Verificado com
duas réplicas contra um Redis real: **1 job enfileirado** com o default, **2** com
`unique=False`. O `arq` coordena com a unicidade da chave no Redis o que o Quartz
coordena com uma tabela de locks — sem lock explícito.

O que ele **não** resolve: relógios fora de sincronia entre réplicas produzem
`next_run` diferentes, logo ids diferentes, logo duas execuções. Aqui isso é
inofensivo, porque a varredura é idempotente.

## Alternativas consideradas

### Alternativa A — aceitar que não há retry e simplificar o `ProcessTurn`

Apagar `MAX_TRIES`, `final_attempt` e o ramo morto; `_tratar_falha` sempre marca
falha. Honesto com o que a biblioteca faz, e menor.

Rejeitada porque joga fora uma proteção real: a falha antes do primeiro trecho é
tipicamente intermitência de rede, e a segunda tentativa é barata (nada foi
sintetizado, nada foi entregue). O SDK da Anthropic já tenta 2× por dentro, mas
STT e storage não têm retry nenhum. O custo da alternativa escolhida é uma linha
de tradução no worker; o da A é um turn perdido a cada blip de rede no MinIO.

### Alternativa B — deixar o retry quebrado e cobrir tudo com a varredura

Não tocar no `ProcessTurn` neste card; registrar como dívida.

Rejeitada porque força o prazo da varredura para o lado curto. Com o caminho
normal de falha fechando sozinho em ~1 min, 5 min de prazo cobrem só o worker
morto; sem isso, a varredura vira o único mecanismo e teria de rodar em ~90 s
para não deixar o aluno esperando — e aí ela passa a matar turns que estavam
apenas demorando, que é o modo de falha que o card mais queria evitar.

### Alternativa C — `list_stale` devolvendo `Turn` com `selectinload`, como o card previa

Uma query só, sem N+1.

Rejeitada por corretude, não por gosto: a foto não fecha a corrida (ver Decisão
4). O custo aceito é 1 + N queries num caminho raro e com lote limitado.

### Alternativa D — fechar a corrida com `SELECT ... FOR UPDATE`

Travar a linha na leitura, eliminando a janela entre o `get` e o `commit`.

Rejeitada por ora: a janela residual é de milissegundos, e o pior desfecho dela é
um turn `completed` virar `failed` **com os trechos preservados** — o aluno já
ouviu tudo. Um lock de linha no caminho de uma varredura que roda com
`MAX_JOBS = 1` acrescenta um modo de falha (contenção com o worker vivo) para
fechar uma janela cujo custo é menor que ele. Gatilho para reabrir: qualquer
ocorrência observada de `ignorados > 0` acompanhada de reclamação de aluno.

## Consequências

**Positivas**

- O caminho de falha mais provável do produto passa a ter dono, e por dois
  mecanismos independentes: o retry real (~1 min) e a varredura (5 min).
- `MAX_TRIES` e `final_attempt` deixam de ser decoração; o teste que os cobria
  deixa de passar por um motivo falso.
- A marcação de falha tem um dono só — o CARD-032 ("Descartar") e o CARD-034
  (encerramento de sessão) herdam a receita em vez de recopiá-la.
- A ignorância sobre o `arq` que este ADR desfaz está **presa em testes** contra
  um `arq` real: se a biblioteca mudar de comportamento, eles apontam.

**Negativas**

- Uma exceção a mais no vocabulário de `application`, e uma tradução no worker
  que alguém tem de lembrar de manter — se a captura sumir, o retry volta a não
  existir, **em silêncio**. Mitigado pelo teste que conta as chamadas.
- 1 + N queries na varredura. Irrelevante hoje, e o gatilho para revisitar é
  medição, não intuição.
- Um turn pode ser encerrado por prazo enquanto ainda estava vivo, se o pior caso
  legítimo crescer (um `teacher_timeout_seconds` maior, um áudio mais longo). A
  conta está no `config.py` justamente para que mexer nesses valores mostre o
  prazo que precisa mudar junto.
- `run_at_startup` fica falso, então a primeira varredura depois de uma subida
  espera a virada do minuto. Aceito: varrer no boot pegaria turns legitimamente
  em voo durante um deploy.

**Equivalente mental .NET**

`cron_jobs` é um `IHostedService` com `PeriodicTimer` — com uma diferença que
importa: o que ele faz na hora marcada é **enfileirar**, e o `job_id`
determinístico dá de graça a coordenação entre réplicas que no .NET custa Quartz
com cluster. E `arq.Retry` não tem análogo direto: no MassTransit/Hangfire o
retry é política declarada fora do handler; aqui é uma exceção específica que o
código levanta de propósito.
