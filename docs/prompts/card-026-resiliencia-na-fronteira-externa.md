# Prompt — CARD-026: a requisição crua deixa de existir, e um retry que ninguém tinha aparece

- **Tipo:** prompt de sessão, complemento de `/executa-card 026`
- **Escrito em:** 2026-08-27, na sessão que cruzou o guia arquitetural externo com o backlog
- **Status:** não executado

> **Este prompt não substitui o `/executa-card`.** Aquele comando carrega o
> protocolo (branch, ordem de leitura, premissas antes do plano, DoD item a
> item, convenção de commit). **Rode `/executa-card 026` e leia isto junto** —
> aqui está a arqueologia já feita, **um achado que pode invalidar uma premissa
> do card antes da primeira linha de código** (§3.3), e as armadilhas que custam
> a sessão inteira se descobertas tarde.

---

## 0. Antes do plano: a fila de perguntas

Última sessão executada: **CARD-014** (PR #20). Ela **não deixou pergunta sem
desfecho** — as três decisões foram feitas no ponto da decisão e respondidas, e a
Q15 foi dispensada pelo desenvolvedor e arquivada com evidência.

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

### 3.2 O que o card assume e você deve confirmar antes de planejar

| O card diz | Confirme assim |
|---|---|
| *"defaults do botocore: 60 s connect, 60 s read, 5 tentativas"* | Não confie no prompt. `python -c "from botocore.config import Config; print(Config().connect_timeout, Config().read_timeout, Config().retries)"` no venv do projeto, e cole o resultado no card |
| *"quatro adapters dividem o mesmo pool"* | `grep -rn "run_in_executor(None" src` — são STT, TTS, encoding e storage. O tamanho do pool default é `min(32, os.cpu_count() + 4)`; imprima o número da máquina onde você vai medir |
| *"120 s por turn com o provedor morto"* | Depende inteiramente da §3.3. **Meça, não multiplique** |

### 3.3 O achado que pode invalidar a premissa do problema 3 — **confirme primeiro**

Lendo o `arq` 0.28 instalado (`.venv/.../arq/worker.py`), o retry parece **não
acontecer para exceção comum**:

- a docstring de `Retry` (linha 97) diz *"Special exception to retry the job"*;
- no `except` do `run_job` (linha ~613), só `Retry`, `CancelledError` e
  `RetryJob` caem no ramo de retry. **Exceção comum cai no `else`**: loga
  `failed`, `finish = True`, `jobs_failed += 1`;
- `max_tries` (linha 549) é usado como **teto** — aborta o job se `job_try` já
  passou —, não como gatilho;
- e no repositório inteiro **não há um único `raise Retry`**:
  `grep -rn "Retry" src` só acha o comentário.

Se isso se confirmar, três coisas mudam de uma vez:

1. o `MAX_TRIES = 2` do `worker/main.py:62` limita algo que **nunca ocorre**;
2. `final_attempt=tentativa >= MAX_TRIES` é sempre `False`, porque `job_try`
   nunca passa de 1 — então o handler **levanta esperando uma segunda chance que
   não vem**, e o turn fica `processing` até a varredura do CARD-025, **que
   também não existe ainda**;
3. o item 3 do card ("o retry insiste num provedor morto") está **errado no
   diagnóstico e pior na consequência**: não são 120 s de insistência, é um turn
   que morre calado.

**Prove antes de agir.** O caminho mais barato é um teste de integração que
enfileira um job cuja função levanta `RuntimeError` e conta quantas vezes ela é
chamada — 1 ou 2. Se der 1, este card ganha um problema novo (e o CARD-025 ganha
urgência), e isso **vai ao desenvolvedor antes do plano**, porque muda o escopo.

Se der 2, o parágrafo acima está errado e a correção vai para o card — sem drama,
com a evidência colada.

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

### 4.6 O SDK da Anthropic já tem retry próprio, e ele soma com o seu

`AsyncAnthropic(api_key=...)` (em `adapters/llm/factory.py`) usa `max_retries=2`
por default. Empilhar `tenacity` por cima sem zerar o do SDK multiplica as
tentativas e o tempo de parede. **Decida qual das duas camadas retenta e desligue
a outra explicitamente** — e escreva a decisão, porque as duas são invisíveis no
código de quem lê depois.

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
  a decisão da §3.3 (ela muda o card, não é detalhe); o teste de dependência
  lenta com tempo medido.
- **Pode virar card próprio:** o executor separado (§4.3), se a medição mostrar
  que com `MAX_JOBS = 1` o ganho é teórico — mas então **escreva o gatilho**, do
  jeito que o `MAX_JOBS` fez; o breaker, se a §3.3 revelar que o problema real é
  outro.
- **Já está em "Out" e continua:** rate limit e cota (CARD-015); varredura de
  travados (CARD-025); observabilidade das aberturas de circuito.

## 6. Governança

1. **Decisão que os ADRs não cobrem vai ao desenvolvedor ANTES da primeira linha
   de código.** Nesta sessão, no mínimo:

   - **D1 — o resultado da §3.3**, e o que fazer com ele. **Bloqueia o plano**:
     se o retry não existe, o card muda de forma;
   - **D2 — biblioteca ou código próprio** para retry e breaker (§4.5), com o
     dry-run de rebaixamento na mão;
   - **D3 — os números**: timeout de cada adapter, N falhas para abrir o
     circuito, janela de recuperação. Cada um derivado de medição, não de gosto;
   - **D4 — o que o aluno vê** quando o provedor está fora. Motivo novo no
     `Turn.fail`? Desfecho novo no `Result` (e aí a rota e o `assert_never` vão
     junto — o mecanismo do ADR-0039 cobrando exaustividade)? Ou nada visível e
     só log?

2. **Regra do explicador: no máximo 2, no ponto da decisão, sobre consequência
   observável.** Candidatas boas, porque a resposta se confere rodando:

   - *"um job cuja função levanta `RuntimeError`: quantas vezes o `arq` chama a
     função — uma ou duas? E o que isso significa para o `final_attempt` que o
     `process_turn` recebe?"* (§3.3 — é o teste que o card precisa de qualquer
     forma, e responde a pergunta mais cara da sessão);
   - *"com `read_timeout=2` e `retries` não configurado, quanto tempo de parede
     leva um `put_object` contra uma porta que engole pacotes — 2 s ou mais? Por
     quê?"* (§4.1 — demonstração de poucos minutos que mata a dúvida de vez).

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

- [ ] **A §3.3 respondida com evidência de execução**, e o card corrigido para
      bater com o que a execução mostrou — nos dois sentidos.
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

> **Cuidado com processos velhos:** aconteceu no CARD-012, no CARD-013 **e no
> CARD-014** — um uvicorn e um worker de horas antes, servindo código antigo.
> Neste card isso é pior que de costume: você vai **medir tempo**, e um processo
> velho sem a configuração nova produz um número que parece bom e não significa
> nada. `ps aux | grep -E "uvicorn|voicecoach-worker"` antes de medir qualquer
> coisa, e derrube o que você subiu ao terminar.

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
