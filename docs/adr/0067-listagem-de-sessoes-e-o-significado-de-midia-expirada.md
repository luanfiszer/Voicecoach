# ADR-0067 — `GET /v1/sessions`, sem cache, e "mídia expirada" significa "não conte com ele"

- **Status:** aceito
- **Data:** 2026-09-13
- **Critério de obrigatoriedade** (`docs/adr/README.md`): **2 — define ou
  altera uma fronteira** (novo recurso de leitura no contrato `/v1`, com
  envelope e janela como parâmetro) e **5 — seria difícil de reverter** (o
  significado de `reply_media_available` é uma afirmação que a tela faz em
  português ao aluno; invertê-lo depois muda o que o app já disse).
- **Relacionado:** ADR-0024 (retenção assimétrica de mídia), ADR-0051 (zero é
  dado, não ausência), ADR-0008 (evolução aditiva), ADR-0063 (quota bloqueia
  escrita, não leitura), ADR-0064 (o precedente de "sem cache, e por quê"),
  CARD-030, CARD-029 (a tela)

## Contexto

O artboard 10 existe desde 2026-08-17 e o servidor não sabia responder a
pergunta dele — *"quais foram minhas sessões?"*. `api/routes/sessions.py`
tinha só `POST`, e o `SessionRepository` não tinha listagem: não era um
endpoint faltando, era uma capacidade de consulta que nunca existiu.

A tela revela, de quebra, uma regra que o backend **tem** e nunca expôs:
*"Áudio expirado — transcrição e correções permanecem"*. Com
`retention_reply_chunk = 1 dia` (ADR-0024), os trechos da conversa de **ontem**
já expiraram — o aviso que o artboard põe na terceira linha é, na prática, o
caso comum.

## Decisão

**1. `GET /v1/sessions?days=30`, com envelope.** A janela é parâmetro com
default de 30 dias — a promessa que a tela faz (*"sessões anteriores a 30 dias
vivem no app web"*) — e o que fica fora dela é **ausência, não erro**. A
resposta é `{sessions: [...], window_days: N}` e não uma lista nua: um array no
topo é um contrato que não cresce, e acrescentar paginação ou "quantas ficaram
de fora" depois exigiria trocar o tipo raiz, que é o que o ADR-0008 proíbe
dentro de `/v1`.

**2. `reply_media_available` é uma PREVISÃO CONSERVADORA, e significa "não
conte com ele".** O card pede a escolha entre dois significados possíveis, e
esta é a razão da escolhida: o lifecycle do S3 apaga *"em até 24h depois"* da
data de expiração, nunca no segundo exato. Então, comparando `last_turn_at +
retenção` com agora:

- **antes**: o áudio certamente está lá → `true`;
- **depois**: ele *pode* estar (janela de graça do bucket) ou não → `false`.

O campo diz `false` a partir do segundo caso. **A direção do erro é
deliberada:** prometer áudio que sumiu deixa o aluno tocando o play e ouvindo
silêncio; esconder áudio que ainda sobreviveria por algumas horas custa uma
reprodução que ninguém sabia estar disponível. Sessão sem turn nenhum é
`false` — não há mídia sobre a qual responder.

**O cliente nunca calcula isto pela data.** A retenção é configuração; um app
publicado que a tenha embutida passa a mentir no dia em que ela mudar, e o
ADR-0024 já registrou que ela é ajustável.

**3. Duas queries agregadas, não uma.** `Correction` pende de `Turn`, que pende
de `Session`. Juntar as três num `JOIN` só multiplicaria cada turn pelo número
de correções, e `SUM(audio_duration)` contaria o mesmo áudio N vezes — o
*fan-out* clássico, que **não dá erro: dá um número maior, em silêncio**. Duas
agregações com `GROUP BY` próprio custam uma query a mais e não têm esse modo
de falha. O que o RNF1 exige é que o número **não cresça com o número de
sessões**, e duas é constante — provado por um teste que conta as instruções
executadas (`before_cursor_execute`) com 1 e com 6 sessões.

`outerjoin` e não `join`, para que a sessão aberta e abandonada apareça com
zeros (RF4). Com o join interno ela sumiria — e sumir também não dá erro.

**4. Sem cache, e a decisão é explícita** (RNF4 proíbe silêncio). As duas
agregações são sustentadas pelo índice composto `(student_id, started_at)` que
este card cria. Cachear introduziria uma terceira fonte para divergir do que o
`POST /turns` acabou de escrever, e o gatilho de invalidação seria "qualquer
turn novo" — ou seja, invalidação na mesma frequência em que a tela é aberta.
TTL e gatilho: **não há**. Revê-se se a agregação aparecer como hot path em
profiling real. É o mesmo raciocínio, e o mesmo desfecho, do ADR-0064.

## Alternativas consideradas

### Alternativa A — o cliente deriva "mídia expirada" da data da sessão

Zero campos novos no contrato. Rejeitada: a política de retenção é
configuração do servidor (ADR-0024), e um app na loja com a regra embutida
passa a mentir no dia em que ela mudar — sem que ninguém perceba, porque o
sintoma é um play que não toca.

### Alternativa B — verificar no bucket se o objeto existe (`HEAD` por sessão)

Diria a verdade em vez de prever. Rejeitada por custo e por forma: seria um
`HEAD` por trecho por sessão — o N+1 que o RNF1 proíbe, movido do banco para a
rede — para uma tela que sequer toca o áudio.

### Alternativa C — uma query só, com `JOIN` triplo

Mais curta de escrever. Rejeitada pelo fan-out descrito na decisão 3: ela
devolveria a duração falada multiplicada pelo número de correções, e o erro
não apareceria como falha — apareceria como "o aluno falou 4 minutos" quando
foram 2.

## Consequências

- **Positivas:** o CARD-029 (a tela) deixa de estar bloqueado por ausência de
  servidor; a duração falada da listagem é a **mesma definição** do resumo
  pós-sessão do CARD-031 (soma de `audio_duration`), então "6 min" significa a
  mesma coisa nas duas telas; e a regra de retenção deixa de ser um detalhe de
  infraestrutura invisível para virar um campo do contrato.
- **Negativas:** `reply_media_available` pode dizer `false` para um áudio que
  ainda existe por algumas horas — é o preço aceito da direção do erro. E há
  duas queries onde um `JOIN` daria uma; a alternativa era um número errado em
  silêncio.
- **Equivalente mental .NET:** o `outerjoin` com `GROUP BY` é o `GroupJoin` do
  LINQ (contra o `Join`, que descarta o lado vazio), com a armadilha de que
  aqui o descarte não dá erro — dá uma linha a menos. E o teste que conta
  instruções é o equivalente de um `DbCommandInterceptor` do EF Core usado como
  asserção, não como log.
