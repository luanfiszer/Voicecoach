# CARD-026 — Resiliência na fronteira externa: a chamada crua deixa de existir

- **ID:** CARD-026
- **Épico:** Fase 2 — Proteção de margem (abre a fase)
- **Plataforma:** backend · **Esforço:** M · **Status:** backlog
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
um, porque nada guarda que o provedor está fora. O guia §01: *"Circuit Breaker
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
