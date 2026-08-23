# ADR-0036 — O primeiro consumidor revela o que faltava nas portas

- **Status:** aceito
- **Data:** 2026-08-23
- **Complementa:** [ADR-0024](0024-midia-por-trecho-chave-url-assinada-e-retencao-assimetrica.md)
  e [ADR-0034](0034-adapter-s3-sincrono-em-executor-e-retencao-por-tag.md) (storage),
  [ADR-0029](0029-o-que-atravessa-a-porta-de-stt-sao-bytes-codificados.md) (STT),
  [ADR-0031](0031-o-que-atravessa-a-porta-do-professor-e-um-fluxo-de-eventos.md)
  (onde o erro mora), [ADR-0004](0004-persistencia-postgres-sqlalchemy-alembic.md)
  (unidade de trabalho)
- **Critérios de obrigatoriedade:** **2 — define ou altera uma fronteira**. Cinco
  fronteiras mudam aqui, e nenhuma delas é detalhe interno de módulo.

## Contexto

As cinco portas do projeto (STT, professor, TTS, storage, repositórios) foram
escritas nos CARDs 005–008, cada uma com adapter e teste próprios. **Nenhuma
jamais tinha sido composta.** O CARD-009 é o primeiro consumidor real, e a
composição revelou cinco lacunas que os testes de porta isolada não podiam
revelar — porque cada um deles exercitava um método por vez, e nenhum precisava
do *conjunto*.

Isto é um ADR e não uma nota de card porque **cada lacuna é uma fronteira**, e
porque a lição vale além destas cinco: uma porta sem consumidor é uma hipótese,
não um contrato. O `MediaStorage` até previa isto por escrito — o docstring dizia
que um `get` entraria *"por extensão, quando o CARD-009 precisar disso, com o
motivo escrito"*.

## Decisão

**As cinco extensões entram, cada uma com o motivo que a força — e o padrão que
elas compartilham fica registrado: quem descobre o que falta numa porta é quem a
consome, não quem a escreve.**

1. **`MediaStorage.get(key) -> bytes`.** O worker precisa do áudio do aluno
   **dentro do processo** para entregá-lo ao STT. A rejeição da alternativa B do
   ADR-0024 (um `get` que devolve bytes) continua válida onde foi escrita: ela é
   sobre a **API** ler o objeto para repassá-lo ao cliente — aí a URL assinada
   perde o propósito, porque o produto volta a pagar banda e CPU de streaming. O
   worker é o oposto: ele é o **destinatário** dos bytes, não um intermediário, e
   uma URL assinada só o faria baixar de si mesmo por HTTP. Assimetria
   deliberada: escrita e leitura direta são do worker, URL assinada é da API.

2. **Porta `AudioEncoder`.** A cascata comprime PCM em AAC antes de gravar
   (ADR-0024), e `to_aac` mora em `adapters/tts/encoding.py` porque usa PyAV.
   `concat` pôde morar em `application` por ser aritmética sobre `bytes`
   (ADR-0033); comprimir não pode. Verificado com o gate: importar `to_aac` no
   caso de uso reprova **dois** contratos — `layers`, pela seta que sobe, e o
   `forbidden` de `application`, que alcança `av` **pela cadeia indireta**
   (`use_case → encoding → av`). Logo, ou a compressão vira porta, ou não
   acontece no caso de uso — e não comprimir custa 816 KB por resposta em vez de
   ~136 KB, na rede móvel do aluno. `content_type` e `extension` saem do mesmo
   objeto para que não possam divergir da chave gravada.

3. **`SttError` na porta de STT.** O CARD-006 não a criou porque não havia quem
   capturasse; agora há — o caso de uso precisa marcar o turn como `failed` com
   um motivo, e `application` não pode importar `faster_whisper` nem
   `mlx_whisper`. É a regra do ADR-0031 item 5 aplicada uma quarta vez: **onde o
   erro mora é consequência de quem precisa capturá-lo**. Os dois adapters
   traduzem com `except Exception` amplo e justificado — ao contrário do `boto3`
   (que tem `ClientError`/`BotoCoreError` como raízes), nenhuma das duas
   bibliotecas publica uma família de exceções, e listar só as conhecidas
   deixaria as demais vazarem como tipo de biblioteca.

4. **`TurnRepository.list_by_session(session_id, *, limit)`.** Sem ela o
   professor recebe um histórico de um item e responde como se cada fala fosse a
   primeira da conversa — um produto diferente do pretendido. Devolve **só
   `completed`**: um turn que falhou não tem os dois lados do diálogo, e
   alimentar o professor com metade de uma troca ensinaria a ele um padrão de
   conversa que não existe. `limit` é obrigatório e sem default, porque escolher
   quanto contexto pagar em tokens é decisão de custo (ADR-0010) e não pode ser
   tomada dentro do repositório.

5. **Porta `UnitOfWork`, com `commit` e sem `rollback`.** O docstring dos
   repositórios já dizia que quem comita não é o repositório; faltava dizer quem
   é. Na API será a borda, uma vez por request; **no worker é o caso de uso**, e
   por uma razão que não existia antes da cascata: um trecho que o aluno já ouviu
   tem de estar gravado antes do próximo, porque é dele que a retomada por
   `Last-Event-ID` reconstrói (ADR-0026, item 3). Uma transação só, do início ao
   fim do turn, deixaria os trechos invisíveis exatamente nos ~2 s em que alguém
   pode reconectar. **O turn não é uma transação: é uma sequência de marcos
   confirmados.** Não há `rollback` porque quem descarta a transação é quem a
   abriu (o `async with` da task), e um caso de uso capaz de desfazer um marco já
   confirmado seria uma promessa falsa.

**Equivalente mental .NET:** os itens 1–4 são o que aconteceria ao escrever a
primeira implementação real de uma interface desenhada só contra testes de
unidade. O item 5 é o `IUnitOfWork` explícito que o EF Core esconde atrás do
`SaveChangesAsync` do `DbContext` — com a diferença de que aqui não há change
tracking (ADR-0004), então **cada** marco é um `update` seguido de um `commit`
escritos à mão.

## Alternativas consideradas

### Alternativa A — Não mexer nas portas; resolver tudo no worker

- **O que é:** o worker baixa o áudio por HTTP da própria URL assinada, chama
  `to_aac` direto (é `worker`, pode importar `adapters`), deixa a exceção do
  Whisper subir crua e monta o histórico com uma query própria.
- **Por que foi rejeitada:** move a lógica do pipeline de `application` para
  `worker`, e com ela **a testabilidade**. O critério de aceite do CARD-009 é o
  caso de uso rodar em milissegundos com fakes de todas as portas — 21 testes em
  0,07 s. Um pipeline escrito no worker exigiria Redis, Postgres e modelo real
  para exercitar qualquer caminho triste, e o teste da 3ª sentença falhando
  simplesmente não existiria. É trocar cinco assinaturas por uma suíte que
  ninguém consegue rodar.

### Alternativa B — Uma porta "worker" grossa, com tudo que o pipeline precisa

- **O que é:** em vez de cinco extensões pontuais, uma fachada só
  (`TurnProcessingContext`) que agrega storage, codec, repositório e relógio.
- **Por que foi rejeitada:** é o God Object com nome de padrão. Cada porta atual
  tem exatamente um motivo para mudar e um fake de dez linhas; a fachada teria
  cinco motivos e um fake que ninguém escreve sem copiar o anterior. E destruiria
  o que torna a substituição barata — foi a porta de TTS bem estreita que
  permitiu trocar Kokoro por Piper (ADR-0032) sem tocar em nenhum consumidor.

### Alternativa C — Adiar `list_by_session` e assumir "histórico = só o turno atual"

- **O que é:** registrar a dívida e entregar o card menor.
- **Por que foi rejeitada:** foi levada ao desenvolvedor como decisão de produto,
  porque muda o que o aluno experimenta — um professor sem memória entre turnos.
  A decisão foi **incluir**. Fica registrado que era um corte legítimo de escopo,
  e que não foi feito por escolha explícita, não por omissão.

## Consequências

**Positivas**

- O pipeline inteiro é testável sem infraestrutura: 21 testes, 0,07 s, cinco
  portas dubladas — e o `mypy` reprova qualquer fake que saia de sincronia,
  como reprovou os dois fakes de storage no instante em que `get` entrou.
- Cada extensão tem o motivo escrito **na porta**, não num card: quem abrir
  `media_storage.py` daqui a um ano lê por que a assimetria existe.
- O `UnitOfWork` explícito torna a cadência de commits uma asserção de teste
  (`trechos_por_commit == [0, 0, 1, 2, 3, 3, 3]`) em vez de um detalhe invisível.

**Negativas — o preço aceito**

- **Cinco fronteiras a mais para manter**, e portas são o que mais custa mudar
  depois: cada uma tem adapter, fake e teste de conformidade.
- **`get` na porta de storage é uma porta aberta para o antipadrão que o
  ADR-0024 rejeitou.** Nada impede a API de chamá-lo e voltar a ficar no caminho
  dos bytes. A barreira é só a prosa do docstring — não há gate que a imponha.
- **`UnitOfWork` no caso de uso significa que um turn interrompido deixa estado
  parcial gravado.** É o que o ADR-0023 quer (falhar não apaga trecho), mas
  também significa que não existe "desfazer o turn": qualquer limpeza é
  compensação explícita.
- **`list_by_session` traz os trechos junto**, por obrigação do
  `lazy="raise_on_sql"`, mesmo que o histórico não os use. Um SELECT a mais por
  turn, aceito para não criar um mapeador parcial.
