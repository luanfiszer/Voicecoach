# CARD-026 — Resiliência na fronteira externa: a chamada crua deixa de existir

- **ID:** CARD-026
- **Épico:** Fase 2 — Proteção de margem (abre a fase)
- **Plataforma:** backend · **Esforço:** M · **Status:** concluído (2026-08-30)
- **Dependências:** CARD-009 (concluído), CARD-012 (concluído — a latência
  medida é o critério); ADR-0030, ADR-0034, ADR-0037, ADR-0045

## Contexto

Origem: guia arquitetural externo (§01 *Resiliência na comunicação entre
serviços*), trazido pelo desenvolvedor em 2026-08-27. O guia é de um sistema
distribuído .NET com muitos serviços; aqui há **um** processo de API, **um**
worker e três dependências remotas — Anthropic, S3/MinIO e Redis. A premissa
do guia se aplica com força reduzida, mas o item que ele chama de inegociável
não tem contrapartida neste repositório:

> *"Nunca fazemos uma requisição crua. Toda chamada entre serviços é embrulhada
> em padrões que decidem, de antemão, como o sistema se comporta quando o outro
> lado falha. Esses padrões não são um extra de fim de projeto."*

O projeto já tem **timeout no professor** (`config.py:188`), **retry no job**
(`MAX_TRIES = 2`, com a guarda certa em `process_turn.py`) e **um teto de
concorrência** (`max_jobs` no `WorkerSettings`). O que falta é o resto — e o
que falta tem número.

> **ATUALIZADO PELO CARD-025 (2026-08-29).** Quando este card foi escrito, o
> "retry no job" **não existia**: o `arq` não retenta exceção comum, e o
> `ProcessTurn` levantava a exceção crua achando que ela voltava para a fila —
> medido, 1 chamada, não 2 ([ADR-0052](../adr/0052-o-retry-do-arq-e-explicito-e-a-marcacao-de-falha-mora-num-lugar-so.md)).
> O CARD-025 o fez existir: o caso de uso levanta `RetryableTurnFailureError` e
> `worker/main.py` traduz em `arq.Retry(defer=0)`. **Consequência para este
> card:** a política de retry que ele vai desenhar tem agora um mecanismo real
> em que se apoiar — e o `defer=0` provisório do CARD-025 é exatamente o lugar
> onde o backoff exponencial com jitter deve entrar.

## Problema

**1. O adapter de storage não tem timeout, e o default do botocore é maior que
o turno inteiro.**

`s3_media_storage.py:215` monta o cliente com `Config(signature_version="s3v4")`
e mais nada. Os defaults do botocore são **60 s de connect timeout, 60 s de read
timeout e até 5 tentativas**. O orçamento do turno é **2,4 s** (ADR-0047, p50
medido de 2,34 s no CARD-013). Um MinIO lento não degrada o turno: ele o
**congela por minutos**, dentro da cascata, com o aluno na tela de espera.

Esse é o único lugar do sistema onde o tempo de parede de uma dependência não
tem teto declarado.

**2. Todo trabalho bloqueante divide o mesmo pool de threads.**

`run_in_executor(None, ...)` — executor default — aparece em quatro adapters:
STT (`faster_whisper_adapter.py`), TTS (`piper_adapter.py`), encoding AAC
(`encoding.py`) e storage (`s3_media_storage.py`). É um pool só. Um upload
pendurado nos 60 s do item 1 segura uma thread de que o STT do próximo turno
precisa. É exatamente o efeito dominó do guia — em miniatura, dentro de um
processo: *"um serviço travado segura conexões, que seguram threads"*. O
`max_jobs` protege a fila; ele não protege o pool.

**3. Não existe circuit breaker, e o retry atual insiste num provedor morto.**

Com a Anthropic fora do ar, cada turn paga `teacher_timeout_seconds × 2`
tentativas do SDK × `MAX_TRIES = 2` — até **~120 s** de espera por turn
(`config.py:184-188` já documenta o 3× do SDK) — e todos os alunos pagam, um a
um, porque nada guarda que o provedor está fora.

> **CORRIGIDO PELO CARD-025:** até 2026-08-29 o fator `MAX_TRIES = 2` **não se
> aplicava** (o retry não existia), então o pior caso real era ~60 s, não ~120 s.
> Com o retry agora funcionando, **os ~120 s passaram a ser verdade** — e o
> `defer=0` os torna consecutivos, sem espera entre as tentativas. Isso reforça
> a urgência do circuit breaker em vez de reduzi-la. O guia §01: *"Circuit Breaker
impede insistir num serviço morto"*.

**4. Não está escrito o que o aluno vê.** Hoje o desfecho é `failed` com motivo.
Isso é o comportamento correto para falha real; não é o comportamento correto
para *provedor indisponível*, que é um estado transitório e conhecido.

## Proposta técnica

- **Timeout explícito em toda saída de rede, configurável, sem default herdado.**
  No storage: `Config(connect_timeout=..., read_timeout=..., retries={...})` —
  os três juntos, porque configurar timeout e deixar `retries` no legacy mode
  multiplica o timeout por 5. Valores derivados do orçamento de latência, com a
  conta escrita no card, não estimada.
- **Retry com backoff exponencial + jitter** onde ele é seguro — e a pergunta
  do guia (*"o que acontece se isso rodar duas vezes?"*) respondida por
  operação. O `put_object` é idempotente por `(bucket, key)` e a chave é
  derivada do turn (ADR-0024): repetir sobrescreve o mesmo objeto com o mesmo
  conteúdo. O professor **não** é idempotente e o ADR-0030 já proíbe retry
  depois do primeiro `yield`.
- **Circuit breaker no adapter do professor**, na fronteira, sem entrar no
  núcleo — o caso de uso continua vendo uma porta que ou entrega eventos ou
  levanta. Aberto o circuito, a falha é **imediata e barata** em vez de custar
  120 s por aluno.
- **Bulkhead de verdade: executor próprio por classe de trabalho.** No mínimo
  separar o pool de I/O (storage) do pool de CPU (STT/TTS/encoding), que é a
  divisória que o item 2 mostra faltando. `run_in_executor(None, ...)` vira
  `run_in_executor(self._executor, ...)`.
- **Onde isso mora.** Portas e caso de uso **não mudam** — resiliência é
  detalhe de infraestrutura e o núcleo não pode saber que existe circuito
  aberto. A decisão de biblioteca (`tenacity`? `purgatory`/`aiobreaker`? à mão?)
  entra no ADR, com o critério de sempre: o que ela custa em dependência contra
  o que substitui em código.

> **Isto vira ADR** — critérios 1 (dependência externa nova), 2 (comportamento
> da fronteira porta/adapter) e 5 (difícil de reverter: timeout mal calibrado
> transforma lentidão em falha em produção).

## Escopo

- **In:** timeout explícito nos três adapters remotos; política de retry
  declarada por operação com a pergunta de idempotência respondida; circuit
  breaker no professor; separação de executor; o desfecho de "provedor
  indisponível" distinto do de "falha do turn"; testes com dependência lenta e
  com dependência morta.
- **Out:** rate limit e quota (CARD-015 — são proteção *contra o cliente*, não
  *contra a dependência*); varredura de travados (CARD-025, que é a rede de
  segurança de última instância, não substituto disto); retry do lado do app
  (CARD-012 já decidiu); observabilidade das aberturas de circuito (entra
  quando houver telemetria).

## Critérios de aceite

- **Dado** um storage que não responde, **quando** a cascata tenta gravar um
  trecho, **então** a chamada aborta no timeout configurado — verificável em
  teste, com o tempo medido, e **abaixo do orçamento do turno**.
- **Dado** um storage lento, **então** o STT de outro turn continua obtendo
  thread (o pool de CPU não foi consumido por I/O).
- **Dado** o professor indisponível em N chamadas seguidas, **quando** chega o
  turn N+1, **então** ele falha **sem abrir conexão** e em tempo desprezível.
- **Dado** o circuito aberto, **quando** passa a janela de recuperação,
  **então** a chamada seguinte tenta de novo (o circuito não fica aberto para
  sempre).
- **Dado** um `put_object` repetido pela política de retry, **então** o objeto
  final é o mesmo e nenhum trecho duplicado aparece no turn.
- **Dado** um provedor indisponível, **então** o motivo registrado no turn
  distingue isso de uma falha de conteúdo.

## Riscos

- **Timeout curto demais transforma lentidão em falha.** É o mesmo risco central
  do CARD-025 e a mitigação é a mesma: a conta escrita, derivada do p50 medido,
  não um número redondo escolhido por gosto.
- **Circuit breaker com estado em processo não é global.** Com uma réplica de
  worker é irrelevante; com duas, cada uma abre o próprio circuito. O card deve
  **escrever** isso em vez de fingir que o estado é compartilhado — e dizer o
  que mudaria (estado no Redis) se um dia importar.
- **Dependência nova por pouco código.** Um breaker é ~40 linhas; uma biblioteca
  é uma dependência para sempre. O ADR tem de defender a escolha nos dois
  sentidos.
- **Complexidade que não se paga.** Bulkhead num processo com `MAX_JOBS = 1` é
  quase teórico hoje. O argumento a favor é o item 2 ser real **agora**, não
  quando escalar — o pool é compartilhado com um job só.

## Objetivo de aprendizado

Como Python faz o que o Polly faz em .NET — e onde a analogia quebra. Em
particular: o `ThreadPoolExecutor` por trás do `run_in_executor` **não** é o
`ThreadPool` do .NET com work-stealing (é um pool fixo, e passar `None` significa
*o mesmo pool para todo mundo*), e a razão de `asyncio` não ter um equivalente a
`HttpClientFactory` com handlers encadeados — em Python a política de resiliência
é composta por decorator ou por wrapper explícito, não por pipeline registrado no
contêiner de DI.

---

## Execução (2026-08-30)

- **Status:** concluído
- **Branch:** `card-026-resiliencia-na-fronteira-externa`
- **ADR:** [ADR-0053](../adr/0053-a-fronteira-externa-tem-teto-e-o-professor-tem-disjuntor.md)
- **Custo:** US$ 0,00 — nenhuma chamada à Anthropic. "Morto" e "lento" são um
  socket que aceita e não responde; o resto é fake e MinIO local.

### O achado que mudou o card: a requisição crua estava no professor, não no S3

O card apontava o storage sem timeout (verdade, e corrigido). Mas o adapter do
professor **não capturava exceção nenhuma**, e `AnthropicError` herda de
`Exception`, não de `RuntimeError` — logo nenhuma casava com
`FALHAS_DE_INFRAESTRUTURA`. Com a Anthropic fora do ar, a exceção atravessava o
caso de uso inteiro: o turn não virava `failed`, o retry do CARD-025 não era
pedido, e o aluno esperava até a varredura o encerrar 5 min depois. Era o único
adapter dos cinco sem tradução de erro, e o único que fala com provedor pago.

### As medições (o que substituiu os chutes)

Defaults do `botocore`, contra um socket que aceita e nunca responde:

| Configuração | Tempo de parede |
|---|---|
| como estava (60 s read, `retries` no default `legacy`) | **315 s** |
| `read_timeout=2` sem tocar em `retries` (o erro comum) | 21 s |
| escolhido: `read_timeout=3`, `max_attempts=1`, `standard` | ~9 s |

Os 315 s são **maiores que o `stale_turn_after` de 5 min**: a varredura vinha
matando turns antes de o `put_object` desistir.

Lei do retry do botocore, medida nos dois modos: **conexões = `max_attempts` + 1**
(o botocore normaliza `max_attempts=1` em `total_max_attempts=2` — o nome do
parâmetro é que mente). Cada tentativa custa ainda ~1,2 s no `put_object`, do
`Expect: 100-continue`.

`put_object` real contra o MinIO, 10 amostras por tamanho:

| Tamanho | p50 | max |
|---|---|---|
| trecho típico ~10 KB | 3,6 ms | 4,3 ms |
| ~64 KB | 3,0 ms | 3,6 ms |
| reply/full ~256 KB | 5,1 ms | 5,7 ms |
| patológico ~2 MB | 19,4 ms | 23,6 ms |

Camadas de retry, com o provedor morto: `max_retries=2` do SDK são **3**
requisições HTTP (não 2); × 2 execuções da task pelo `arq` = **6 requisições e
90 s**. Com `teacher_max_retries=1`: 2 × 2 = 4 requisições, 60 s.

### Critérios de aceite

| Critério | Desfecho | Evidência |
|---|---|---|
| storage que não responde aborta no timeout, abaixo do orçamento | ✅ | `test_storage_que_nao_responde_aborta_no_teto_configurado` mede e afirma o teto |
| storage lento não consome o pool de CPU | ✅ **parcial** | pool próprio do storage (`test_o_storage_de_producao_tem_pool_proprio_e_ele_fecha`). STT/TTS/encoding seguem no pool default — ver dívidas |
| professor indisponível em N chamadas ⇒ N+1 falha sem abrir conexão | ✅ | `test_com_o_circuito_aberto_a_falha_e_imediata_e_SEM_ABRIR_CONEXAO` conta invocações de `stream()`: para em 3 |
| vencida a janela, a chamada seguinte tenta | ✅ | `test_vencida_a_janela_a_chamada_seguinte_tenta_de_novo` |
| `put_object` repetido não duplica trecho | ✅ | idempotente por `(bucket, key)` derivada do turn (ADR-0024); o índice do trecho vem de `len(turn.audio_chunks)`, não do retry |
| motivo distingue indisponibilidade de falha de conteúdo | ✅ | `PROVEDOR_INDISPONIVEL`, com os dois lados testados |

### Gates (todos verdes, em `backend/`)

```
uv run ruff format --check src tests   117 files already formatted
uv run ruff check src tests            All checks passed!
uv run mypy                            Success: no issues found in 115 source files
uv run lint-imports                    Contracts: 4 kept, 0 broken.
uv run pytest --cov --cov-fail-under=80    378 passed — Total coverage: 93.27%
uv run coverage report --include="*/domain/*,*/application/*" --fail-under=90   99%
```

**O gate morde** (injetada a violação e revertida): `from
voicecoach.adapters.resilience import CircuitBreaker` em
`application/use_cases/fail_turn.py` ⇒ *"voicecoach.application is not allowed to
import voicecoach.adapters"*.

### Regra do explicador

Duas perguntas feitas **no ponto da decisão**, antes de qualquer código, sobre
consequência observável (§6 do prompt do card):

- **Q1** — *"com `read_timeout=2` e `retries` não configurado, quanto tempo de
  parede leva um `put_object` contra uma porta que engole pacotes?"*
- **Q2** — *"com o provedor morto, quantas requisições HTTP saem, e quantas
  vezes a task inteira roda?"*

**Desfecho das duas: dispensadas pelo desenvolvedor** (*"pula as perguntas"*) —
registradas como dispensa, nunca como cumpridas (LEARNING-0004). Os experimentos
rodaram assim mesmo porque bloqueavam os números, e o resultado está preso em
teste: `test_o_numero_de_tentativas_e_max_attempts_MAIS_UM` e
`test_storage_que_nao_responde_aborta_no_teto_configurado`.

### Dívidas declaradas

| Dívida | Gatilho / card |
|---|---|
| STT, TTS e encoding continuam no pool default | medição mostrando contenção de thread; hoje são ~2 threads contra um pool de 14 |
| `PROVEDOR_INDISPONIVEL` é contrato por string, não campo estruturado | **CARD-027** (tem a tela e sabe de quantos casos precisa) |
| Breaker com estado por processo | mais de uma réplica de worker chamando o professor (ADR-0053, alternativa C) |
| Folga do `stale_turn_after` caiu para ~1,70× | refazer a conta ao mexer em `teacher_timeout_seconds`, `teacher_max_retries`, `s3_read_timeout` ou `s3_max_attempts` |
