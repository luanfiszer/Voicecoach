# ADR-0034 — Adapter S3 síncrono num executor, e retenção por tag em vez de prefixo

- **Status:** aceito
- **Data:** 2026-08-23
- **Complementa:** [ADR-0024](0024-midia-por-trecho-chave-url-assinada-e-retencao-assimetrica.md)
  (que decidiu o esquema de chaves e a retenção assimétrica, mas não como
  expressá-la), [ADR-0014](0014-health-check-liveness-readiness.md) (cuja dívida
  do check de MinIO fecha aqui), ADR-0006, ADR-0010, CARD-008, CARD-017
- **Critérios de obrigatoriedade:** **1 — introduz dependência externa**
  (`boto3`); **2 — altera uma fronteira** (a retenção deixa de ser expressável
  por prefixo e passa a exigir tag por objeto, o que muda o contrato do `put`);
  **4 — afeta privacidade** (é o mecanismo que faz a retenção de voz do
  ADR-0024 de fato acontecer).

## Contexto

O ADR-0024 decidiu **o quê**: chave ordenável por trecho, URL assinada junto do
evento, retenção assimétrica (input 7 dias, trecho 1 dia, `full` 90 dias). O
CARD-008 implementou, e três perguntas que nenhum ADR respondia apareceram no
caminho — duas de forma e uma que contradiz uma suposição do próprio ADR-0024.

1. **`boto3` é síncrono, e o worker é assíncrono.**
2. **A retenção assimétrica não é expressável com o esquema de chaves que o
   ADR-0024 fixou.** As chaves começam pelo `student_id`, então **não existe
   prefixo comum** que selecione "todos os inputs" ou "todos os trechos" — cada
   aluno tem o seu. E o lifecycle do S3 filtra por prefixo **ou tag**; não por
   sufixo, não por padrão. O ADR-0024 escreveu a tabela de retenção supondo, sem
   dizer, que ela seria uma regra de prefixo.
3. **Ninguém criava o bucket.** `s3_bucket` existia só na configuração.

## Decisão

### 1. `boto3` chamado dentro de um executor, não direto da corrotina

**Medido, não argumentado** — 5 objetos de 2 MB contra o MinIO local, com um
heartbeat que deveria acordar a cada 10 ms:

| | upload | voltas do heartbeat | pior atraso |
|---|---|---|---|
| `put_object` direto na corrotina | 122 ms | **0** | **nunca rodou** |
| `put_object` em `run_in_executor` | 93 ms | 10 | 1,0 ms |

Durante os 122 ms, **nenhuma outra corrotina do worker existiu** — num worker em
cascata, é exatamente o intervalo em que a próxima frase deveria estar sendo
sintetizada.

**O argumento do ADR-0029/CARD-006 não transfere, e é importante dizer por quê.**
Lá o `run_in_executor` valia porque o CTranslate2 é CPU-bound e **solta o GIL**
em código nativo — a thread trabalha de verdade em paralelo. Aqui o trabalho é
IO de rede: o GIL até é solto, mas quem não cede o controle é a **corrotina**.
`await` é cooperativo, e uma chamada síncrona nunca coopera. São dois motivos
diferentes para a mesma ferramenta, e confundi-los levaria a otimizar a coisa
errada.

### 2. A retenção é uma **tag por objeto**, derivada da chave

Cada `put` grava `retention={input|reply-chunk|reply-full}`, deduzido da própria
chave, e as três regras de lifecycle filtram por essa tag. **A tag é derivada e
não recebida por parâmetro** porque esquecer de passá-la não daria erro nenhum:
só faria o áudio de voz de um aluno viver para sempre — vazamento de retenção
silencioso, no dado mais sensível do produto. Chave fora do esquema **levanta**
em vez de gravar sem classe.

### 3. O bucket é criado por um sidecar do Compose, não pela aplicação

Um serviço `createbuckets` roda `mc mb --ignore-existing` e sai. A aplicação
nunca cria bucket: em S3 real, a credencial do produto deve poder ler e escrever
objetos e **nada além disso**, e criar bucket é administração.

### 4. As regras de lifecycle são código de setup lendo `Settings`

Os TTLs moram na configuração (o ADR-0024 os fixou assim). O Compose não lê
`Settings`; duplicá-los ali criaria duas fontes de verdade para a única política
do projeto que é obrigação legal.

### 5. O readiness do MinIO passa a ser `head_bucket` com credencial

A dívida que o ADR-0014 registrou com gatilho explícito ("quando o CARD-008
trouxer o cliente S3") fecha aqui. Verificado: bucket inexistente → **404**,
credencial errada → **403**. O probe antigo respondia 200 nos dois casos.

## Alternativas consideradas

### Alternativa A — `aioboto3` em vez de executor

- **O que é:** IO async de verdade, sem thread.
- **Por que foi rejeitada:** arrasta o `aiobotocore`, que **fixa a versão do
  `botocore`** — a fonte mais comum de conflito de resolução nesse ecossistema.
  Para 3 a 6 uploads por turn, com o executor entregando 1 ms de atraso máximo
  medido, a thread é mais barata que o acoplamento de versões. **Gatilho para
  reavaliar:** upload deixar de ser *fire-and-forget*, ou o `aiobotocore` passar
  a acompanhar o `botocore` sem defasagem.

### Alternativa B — Mudar o esquema de chaves para permitir lifecycle por prefixo

- **O que é:** `input/{student}/...` e `reply/{student}/...` — o tipo primeiro,
  o aluno depois.
- **Por que foi rejeitada:** destruiria o `delete_prefix` por aluno, que é o
  mecanismo do delete de conta (LGPD, CARD-017): apagar um aluno passaria a ser
  N varreduras, uma por tipo. Trocaria um problema resolvido por um pior, e
  exigiria substituir o ADR-0024 inteiro em vez de complementá-lo.

### Alternativa C — Retenção por rotina própria (cron que varre e apaga)

- **O que é:** ignorar o lifecycle do bucket e apagar por conta.
- **Por que foi rejeitada:** é literalmente o que o ADR-0006 rejeitou ao escolher
  S3 ("lifecycle/expiração viram cron caseiro"). Uma rotina que não roda não
  avisa — e o modo de falha é guardar voz além do prazo declarado.

### Alternativa D — `types-boto3` em vez de override do `mypy`

- **O que é:** o pacote de stubs, casado versão a versão com o `boto3`.
- **Por que foi rejeitada:** uma dependência a mais, com sincronia manual de
  versão, para tipar **um atributo privado** de uma classe cujo contrato público
  (a porta `MediaStorage`) já está inteiramente tipado. O projeto tem precedente
  de override pontual em `asyncpg` e `faster_whisper`. **Gatilho:** o `boto3`
  publicar `py.typed`, ou o adapter crescer a ponto de o `Any` esconder erro.

## Consequências

**Positivas**

- O event loop do worker continua vivo durante o upload — verificado por teste,
  não por argumento (`test_o_upload_nao_bloqueia_o_event_loop`).
- A retenção do ADR-0024 passa a ser **executável e verificável**: o teste lê as
  três regras de volta do bucket e as compara com `Settings`.
- Esquecer a tag virou impossível: ela é derivada da chave, e chave fora do
  esquema não grava.
- O readiness deixa de mentir nas três falhas que derrubam o primeiro turn do
  dia: credencial, bucket e permissão.
- `delete_prefix` pagina (o S3 lista e apaga no máximo 1.000 por chamada), então
  o delete de conta do CARD-017 não tem teto silencioso.

**Negativas — o preço aceito**

- **Uma thread por operação de storage em voo.** Com o executor default do
  asyncio, isso é o pool compartilhado do processo; um pico de uploads pode
  enfileirar. Aceitável no volume atual (3–6 por turn), e o gatilho para trocar
  por `aioboto3` está escrito acima.
- **`Any` no cliente do adapter.** O `boto3` monta os clientes em runtime a
  partir de JSON, e sem `types-boto3` não há tipo a nomear. O contrato que
  importa está tipado; o atributo privado, não.
- **Tag por objeto custa uma chamada a mais de metadado no `put`** (embutida no
  mesmo request) e amarra a retenção a uma convenção de string. Um objeto
  gravado por fora do adapter — por `mc` na mão, por exemplo — **não** teria a
  tag e viveria para sempre. Não há defesa técnica contra isso; há o teste, que
  falha se o adapter parar de marcar.
- **MinIO não é S3.** Tudo aqui foi verificado contra MinIO, inclusive as regras
  de lifecycle — que é justamente a área onde o ADR-0006 e o ADR-0024 já
  avisavam que as implementações divergem. Na AWS a expiração é assíncrona e
  pode ocorrer até 48 h depois do prazo. **Revalidar no provedor real ao migrar
  continua sendo dívida em aberto**, agora com três regras em vez de duas.
- **O sidecar cria o bucket; o teste de integração o cria de novo por conta.**
  São dois caminhos para a mesma coisa, e eles podem divergir (o teste usa outro
  nome de bucket, de propósito). Aceito: o alternativo seria o teste depender do
  Compose, contra o ADR-0018.

**Equivalente mental .NET:** é `Task.Run(() => blockingSdkCall())` para tirar um
SDK síncrono do caminho do `SynchronizationContext`, com a diferença de que aqui
não há contexto a capturar — e a política de retenção é o *management policy* do
Blob aplicada por **índice de tag**, porque o caminho do blob não tem como
distinguir os tipos.
