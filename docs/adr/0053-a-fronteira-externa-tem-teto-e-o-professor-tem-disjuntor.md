# ADR-0053 — A fronteira externa tem teto, e o professor tem disjuntor

- **Status:** aceito
- **Data:** 2026-08-30
- **Critério de obrigatoriedade** (`docs/adr/README.md`): **critério 2 — define
  ou altera uma fronteira** (nasce `TeacherUnavailableError` na porta do
  professor, e o comportamento de disponibilidade da fronteira porta/adapter
  muda para todo consumidor) e **critério 5 — difícil de reverter** (timeout mal
  calibrado transforma lentidão em falha, e só aparece em produção; desfazer
  exige recalibrar tudo, inclusive o prazo do ADR-0052).
  O **critério 1 não se aplica**, e isso é parte da decisão: nenhuma dependência
  externa entra (ver Decisão 2).

## Contexto

O guia arquitetural externo que originou o CARD-026 diz que *"nunca fazemos uma
requisição crua"*. O projeto tinha timeout no professor, `MAX_JOBS = 1` e, desde
o CARD-025, um retry de fila que funciona (ADR-0052). Faltava o resto — e o que
faltava tinha número.

**A arqueologia encontrou o buraco num lugar diferente do que o card procurava.**
O card apontava o storage sem timeout. Verdade. Mas o adapter do professor
**não capturava exceção nenhuma**, e a hierarquia do SDK é
`AnthropicError -> Exception`, não `RuntimeError`:

| Adapter | Traduz erro do SDK? |
|---|---|
| STT (`faster_whisper`) | sim → `SttError` |
| TTS (`piper`) | sim → `TtsError` |
| encoding (`av`) | sim → `AudioEncodingError` |
| storage (`boto3`) | sim → `MediaStorageError` |
| **professor (`anthropic`)** | **não** |

Como nenhuma exceção do SDK herda de `RuntimeError`, nenhuma casava com
`FALHAS_DE_INFRAESTRUTURA` (`process_turn.py`). Consequência medida: com a
Anthropic fora do ar, a exceção atravessava o caso de uso inteiro sem ser
capturada — o turn **não** era marcado `failed`, o retry do CARD-025 **não** era
pedido, e o aluno ficava na tela de espera até a varredura o encerrar 5 minutos
depois. O único adapter que fala com um provedor remoto pago era o único cru.

**E os defaults do `botocore` custavam mais que o prazo da varredura.** Medido
contra um socket que aceita a conexão e nunca responde:

| Configuração | Tempo de parede |
|---|---|
| como estava (60 s read, `retries` no default `legacy`) | **315 s** |
| `read_timeout=2` sem tocar em `retries` (o erro comum) | 21 s |
| `read_timeout=3`, `max_attempts=1`, `mode="standard"` | ~9 s |

Os 315 s são **maiores que o `stale_turn_after` de 5 min**: a varredura vinha
matando turns antes de o `put_object` desistir. O teto não estava só alto —
estava fora da escala do resto do sistema, e a conta do ADR-0052 justificava um
prazo que não podia funcionar.

## Decisão

**1. Duas camadas de retry, e a terceira não nasce.** O card cogitava
`tenacity`; ela não entra.

| Camada | O que reexecuta | Antes | Agora |
|---|---|---|---|
| SDK da Anthropic | a requisição HTTP | `max_retries=2` (**3 requisições**) | `teacher_max_retries=1` (2 requisições) |
| uma nossa, no adapter | a chamada ao provedor | — | **não existe** |
| `arq` (`MAX_TRIES = 2`) | o turn inteiro | ligada (ADR-0052) | ligada |

Medido: `max_retries=2` são 2 *retentativas*, logo **3 requisições HTTP** — 3
conexões aceitas por um socket que derruba. Com o retry do `arq` por cima, o
default dava **6 requisições e 90 s de professor** por turn contra um provedor
morto.

`1` e não `0` porque é a única das três que lê o cabeçalho `retry-after` de um
429/529 e espera o que o provedor pediu (`_calculate_retry_timeout` do SDK). `1`
e não `2` porque a segunda repete o que o `arq` já faz — e o `arq` faz melhor: a
tentativa dele sobrevive ao processo morrer e cobre também STT e storage, que
não têm retry nenhum.

**2. O breaker é código próprio (`adapters/resilience.py`), ~50 linhas.** Não é
economia de dependência: é que **nenhuma biblioteca embrulha a coisa que
temos**. O professor é um gerador assíncrono com ponto de não-retorno
(ADR-0030): a janela em que falhar significa "provedor fora" termina quando o
`__aenter__` devolve o stream. Toda biblioteca de breaker do ecossistema decora
uma *corrotina*, cujo desfecho é um só, no fim. Aplicada aqui, ela contaria como
falha do provedor um erro ocorrido depois de o aluno já estar ouvindo a
resposta, e abriria o circuito pelo motivo errado.

**3. Timeout do storage com os três parâmetros juntos, ou nenhum.**
`connect_timeout=2 s`, `read_timeout=3 s`, `retries={"max_attempts": 1, "mode":
"standard"}`. A lei, medida: **conexões que saem = `max_attempts` + 1**, nos dois
modos, com o `urllib3` fora do circuito (o botocore o chama com `Retry(False)`).
O "+1" não é arredondamento — é o nome do parâmetro mentindo: o botocore aceita
`max_attempts` e guarda `total_max_attempts = n + 1`, e há teste afirmando isso.
Cada tentativa custa ainda ~1,2 s a mais no `put_object`, do
`Expect: 100-continue`.

Os números saem de medição contra o MinIO, não de gosto: `put_object` de trecho
típico (~10 KB) tem p50 de **3,6 ms**; o caso patológico de 2 MB, **19,4 ms**.
`read_timeout = 3 s` é ~127x o pior caso medido, e a folga é deliberada — o
`read_timeout` do botocore é a espera pela *resposta*, não o tempo de
transferência, então upload lento porém progredindo não o dispara. Errar para o
lado curto transforma turno saudável em falha, que é o risco central do card.

**4. Bulkhead: pool de threads só do storage.** `run_in_executor(None, ...)` usa
*um* pool por event loop (`min(32, cpu+4)` = 14 nesta máquina), compartilhado por
STT, TTS, encoding e storage. O storage passa a receber um `ThreadPoolExecutor`
próprio, montado em `create_media_storage` e **fechado** por `close()`, chamado
em `api/lifespan.py` e no `shutdown` do worker. STT/TTS/encoding continuam no
pool default: com `MAX_JOBS = 1` a separação deles é teórica, e o gatilho para
fazê-la está escrito.

**5. O `defer` do `arq.Retry` continua 0** — a dívida declarada do CARD-025,
fechada por escrito. Com a decisão 1, o backoff que interessa já mora no SDK
(que obedece ao `retry-after`); com a decisão 2, a tentativa seguinte contra um
provedor morto é **instantânea e barata** em vez de esperar. Somar `defer` só
aumentaria o tempo em que o aluno olha uma tela sem saber de nada.

**6. "Provedor indisponível" é um desfecho distinto, e o motivo é constante.**
`TeacherUnavailableError` refina `LlmError` (não é categoria nova ao lado dela),
e o `ProcessTurn` grava a constante `PROVEDOR_INDISPONIVEL` em vez de
`str(exc)`. O que classifica é o **adapter**, que conhece os tipos do SDK; o que
consome é o caso de uso, que conhece só a porta.

## O que a medição corrigiu, e nos dois sentidos

A conta do `stale_turn_after` (ADR-0052) tinha **dois** erros que se compensavam
parcialmente:

- **para menos:** o professor era `30 s × 3 requisições` = 90 s, não os 60 s que
  a conta afirmava. A decisão 1 não "consertou a conta": ela tornou verdadeiro o
  número que a conta já dizia;
- **para mais:** o storage não aparecia na conta de forma nenhuma, porque não
  tinha teto — e o teto real era 315 s por chamada.

Pior caso legítimo recalculado: **~176 s** (era "~146 s" sobre premissas falsas).
Os 300 s são **~1,70×** isso, não os 2,05× escritos. A folga encolheu e o número
fica — porque agora o pior caso é **finito pela primeira vez**.

É a terceira vez que uma conta escrita no meio de uma mudança descreve o sistema
de ontem com a autoridade de um número medido (ADR-0052 registrou as duas
primeiras). O padrão já tem nome no repositório; o que faltava era um teste que
o denunciasse, e agora existe.

## Alternativas consideradas

### Alternativa A — `tenacity` para o retry e uma biblioteca de breaker

O caminho óbvio, e o que o card sugeria.

Rejeitada em duas metades. O **retry** porque seria a terceira camada sobre um
mecanismo que já existe e já foi medido: ela não cobre nada que o SDK e o `arq`
não cubram, e cada camada empilhada multiplica o tempo de parede por um fator
que ninguém escreve em lugar nenhum. O **breaker** pelo motivo técnico da
decisão 2 — a forma do que precisa ser embrulhado (gerador com ponto de commit)
não é a forma que as bibliotecas embrulham (corrotina). Adaptar o gerador à
biblioteca seria mais código que as ~50 linhas, e código de contorno em vez de
código de decisão. O ADR-0038 já mostrou o que uma dependência faz com a versão
de outra.

### Alternativa B — só timeout, sem breaker

Bounded é melhor que unbounded; talvez baste.

Rejeitada porque o timeout resolve o *tempo de cada* chamada e não a *repetição*.
Com `MAX_JOBS = 1` as chamadas são em série: sem breaker, dez alunos pagam 60 s
cada um para descobrir a mesma coisa, um depois do outro. É exatamente o custo
que o breaker existe para não pagar, e ele é linear no número de alunos.

### Alternativa C — estado do breaker no Redis, compartilhado

Fecharia a limitação "cada processo abre o próprio circuito".

Rejeitada por ora: hoje o professor só é chamado do worker, com `MAX_JOBS = 1` —
uma chamada por vez, um processo. O estado compartilhado resolveria um problema
que não existe e acrescentaria uma dependência de Redis no caminho de **toda**
chamada ao professor, inclusive quando tudo está bem. **Gatilho para reabrir:**
mais de uma réplica de worker chamando o professor. O vocabulário a imitar então
não é um lock distribuído — é o que o `arq` faz com `cron_jobs`: uma chave no
Redis cuja unicidade *é* a coordenação (ADR-0052).

### Alternativa D — executor próprio para os quatro adapters

O bulkhead completo que o card descrevia.

Rejeitada por medição, não por preguiça: com `MAX_JOBS = 1` e um consumidor só na
cascata (ADR-0037), o número de threads simultâneas de um turn é ~2 contra um
pool de 14. O dominó do card exige 14 uploads pendurados ao mesmo tempo, o que
o próprio timeout da decisão 3 já impede. Separar o storage (I/O) do resto (CPU)
é a divisória que tem efeito hoje; as outras três esperam gatilho.

## Consequências

**Positivas**

- O caminho de falha mais provável do produto — provedor de LLM fora do ar —
  passa a ter dono. Antes ele **não tinha nenhum**: nem `failed`, nem retry, nem
  mensagem; só a varredura, 5 min depois.
- Nenhum timeout de rede vem de default de biblioteca, e cada número tem a
  medição de origem escrita ao lado.
- Com o circuito aberto, a falha custa microssegundos em vez de 60 s, e
  **nenhuma conexão é aberta** — verificado contando invocações de `stream()`.
- Zero dependências novas. O `pyproject.toml` não muda, e a lista `forbidden`
  do import-linter também não.
- O `CircuitBreaker` é genérico: o CARD-036 (tradução sob demanda) pendura o
  segundo adapter na mesma política sem copiar nada.

**Negativas**

- **O estado do breaker é do processo.** API e worker abrem circuitos
  independentes; duas réplicas de worker, idem. Aceito e escrito, com o gatilho
  na Alternativa C.
- **Um atributo com estado no adapter do professor**, que até aqui não tinha
  nenhum. Não é estado de conversa (o histórico continua entrando por
  parâmetro), mas o teste que garantia "só configuração" precisou ser reescrito
  para dizer qual dos dois casos é qual.
- **O motivo de "provedor indisponível" é um contrato por string**, que é o tipo
  mais fraco que serve. O lugar certo é um campo estruturado no `Failed` e no
  `GET`, com o `assert_never` do ADR-0039 cobrando exaustividade — o que muda
  rota, schema e client TypeScript. Fica para o **CARD-027**, que tem a tela e
  portanto sabe de quantos casos ela precisa. Gatilho: o segundo motivo que o app
  precisar distinguir.
- **A folga do `stale_turn_after` caiu de 2,05× para 1,70×** — sobre um número
  verdadeiro em vez de um falso, mas menor. Se alguém subir
  `teacher_timeout_seconds`, `teacher_max_retries`, `s3_read_timeout` ou
  `s3_max_attempts`, a conta do `config.py` tem de ser refeita.
- **Mais um recurso a fechar no desligamento.** Executor que vaza não dá erro:
  mantém threads vivas e o processo não termina. Mitigado por teste explícito nas
  duas composition roots.
- **STT, TTS e encoding continuam dividindo o pool default.** É dívida
  declarada, com gatilho medido, não esquecimento.

**Equivalente mental .NET, e onde a analogia com o Polly quebra**

No Polly a política é um objeto registrado no contêiner e aplicada pelo
`HttpClientFactory`: o pipeline de handlers fica longe do código de negócio
quase por acidente do framework. Em Python não existe esse acidente — um
decorator é só uma função que embrulha outra, e nada impede que alguém o ponha
em cima de um caso de uso. O `lint-imports` pega o **import**, não o conceito
(ADR-0012, ADR-0052). Daí o breaker ser um objeto explícito chamado em três
pontos nomeados, e não um `@decorator` de uso livre: a forma torna difícil
pendurá-lo no lugar errado.

Duas diferenças menores que custam tempo a quem vem do .NET:

- **`run_in_executor(None, ...)` não é o `ThreadPool` do .NET.** Não há
  work-stealing nem crescimento dinâmico: é um `ThreadPoolExecutor` de tamanho
  fixo, e `None` significa literalmente *o mesmo pool para todo mundo*.
- **O breaker não tem lock, e isso é decisão.** Sob `asyncio`, um método
  síncrono sem `await` dentro roda inteiro entre dois pontos de suspensão — a
  ausência de `await` **é** a região crítica. Em C# o mesmo contador exigiria
  `Interlocked` ou `lock`, porque as threads são preemptivas.
