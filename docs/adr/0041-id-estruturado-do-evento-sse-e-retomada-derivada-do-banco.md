# ADR-0041 — O `id` do evento SSE é estruturado, e a retomada é derivada do banco

- **Status:** aceito — **item 5 completado pelo [ADR-0050](0050-o-feedback-volta-na-retomada-e-o-buraco-do-adr-0041-fecha.md)** (2026-08-26): o gatilho escrito ali era o CARD-013, e ele disparou
- **Data:** 2026-08-23
- **Completa:** [ADR-0026](0026-entrega-progressiva-por-sse-com-polling-como-contrato-de-recuo.md)
  (item 3: *"retomada por `Last-Event-ID`"*, sem dizer qual é o id) e
  [ADR-0035](0035-canal-worker-api-por-pubsub-com-o-banco-como-fonte-da-verdade.md)
  (o banco é a fonte da verdade)
- **Critérios de obrigatoriedade** (`docs/adr/README.md`): **2 — define uma
  fronteira** (o `id:` é parte do contrato de API: o cliente o devolve no
  cabeçalho `Last-Event-ID` e o servidor tem de continuar honrando o formato para
  sempre, sob a política aditiva do ADR-0008).

## Contexto

O ADR-0026 item 1 exige que **todos** os eventos tenham `id` "para permitir
retomada", e o item 3 diz que reconectar reenvia o que faltou "a partir dos
trechos persistidos". Ele não diz **o que é** o id — e as opções não empatam,
porque uma restrição do ADR-0035 elimina a escolha mais natural.

O `Last-Event-ID` é um mecanismo do próprio `EventSource`: o navegador (ou o
polyfill do RN) guarda o último `id:` recebido e o manda sozinho no cabeçalho ao
reconectar. O servidor precisa, a partir daquele valor, saber **onde continuar**.

Os cinco eventos do ADR-0026 não são igualmente reconstituíveis:

| Evento | Reconstituível do banco? |
|---|---|
| `transcribed` | sim — `turn.transcript` |
| `chunk` | sim — `turn.audio_chunks`, com `index` como identidade natural |
| `completed` / `failed` | sim — `turn.status` e os artefatos |
| **`feedback`** | **não** — correções só são persistidas no CARD-013 (ADR-0035) |

## Decisão

**O `id` de um evento é uma string estruturada que o servidor recalcula do
próprio `Turn`: `transcribed`, `chunk:{index}`, `feedback`, `completed`,
`failed`. A retomada compara posições nessa sequência e reemite, do banco, tudo
que vem depois do `Last-Event-ID`.**

1. **A ordem total é a que o pipeline produz de fato** (conferida em
   `process_turn.py`): `transcribed` → `chunk:0..n` → `feedback` →
   `completed | failed`. Ela é calculada por uma função (`posicao`) que devolve
   uma tupla `(família, índice)` — **não** por comparação de strings, ou
   `chunk:10` viria antes de `chunk:2`. É o mesmo bug que o zero-padding das
   chaves de storage evita no bucket (ADR-0024), aqui evitado no código porque o
   id é legível de propósito.
2. **A costura tem ordem obrigatória**, e ela é o item mais fácil de errar deste
   ADR: **assina o canal → lê o banco → emite o histórico → emite o ao vivo**.
   Ler o banco antes de assinar abre uma janela em que um evento publicado se
   perde, porque pub/sub não guarda nada (ADR-0035). É por isso que a porta
   `TurnEvents.subscribe` é um **context manager** e não um `AsyncIterator`: o
   corpo de um gerador assíncrono não executa até a primeira iteração, então
   devolver o iterador direto não teria emitido `SUBSCRIBE` coisa nenhuma.
3. **Deduplicação por id.** O histórico e o canal podem entregar o mesmo evento
   (o trecho já gravado que o worker acabou de publicar). O consumidor guarda os
   ids já emitidos e descarta repetição — sem isso o aluno ouviria frases
   duplicadas.
4. **`Last-Event-ID` fora do esquema é 400**, não "comece do começo". Tratar um
   id inventado como início reentregaria trechos já ouvidos, e o modo de falha
   seria o professor repetindo frases — muito mais confuso de depurar.
5. ~~**`feedback` não volta na retomada.**~~ **COMPLETADO pelo
   [ADR-0050](0050-o-feedback-volta-na-retomada-e-o-buraco-do-adr-0041-fecha.md)**
   em 2026-08-26. Hoje o `feedback` **volta**, reconstruído de
   `turn.corrections`, condicionado a `replied_at`. O texto original fica abaixo,
   porque o gatilho que ele escreveu é o que tornou a reabertura verificável em
   vez de esquecida:

   > **`feedback` não volta na retomada, e isso está escrito.** Um cliente que
   > reconecte depois de o feedback ter passado não o recebe naquele turn; ele o
   > vê no histórico, depois. Inventar um evento vazio seria pior que não mandar
   > nada. **Gatilho para reabrir:** o CARD-013, que persiste as correções — a
   > partir dele o `feedback` passa a ser reconstituível e entra no histórico
   > como os outros.

## Alternativas consideradas

### Alternativa A — Contador monotônico por turn (`id: 1, 2, 3…`)

- **O que é:** um número que cresce a cada evento daquele turn, que é o formato
  que o `EventSource` "espera" idiomaticamente e o mais simples de comparar.
- **A favor:** ordem trivial, sem função de posição; e é o que praticamente todo
  exemplo de SSE na internet faz.
- **Por que foi rejeitada:** **não é derivável do banco.** Na reconexão o
  servidor recebe `Last-Event-ID: 3` e não tem como saber o que foi o evento 4 —
  a tabela `turns` não guarda contador nenhum. Reconstruí-lo exigiria persistir o
  contador (uma coluna e uma escrita a mais por evento, no caminho crítico de
  1,8 s) ou guardá-lo no Redis — que é a **segunda fonte de verdade** que o
  ADR-0035 recusou explicitamente ao rejeitar Redis Streams. O formato mais
  idiomático é o que não cabe na arquitetura já decidida.

### Alternativa B — Redis Streams como origem dos ids

- **O que é:** trocar o pub/sub por um stream por turn; o id da entrada do
  stream vira o `id:` do SSE, e a retomada é `XREAD` a partir dele.
- **A favor:** resolve id e retomada de uma vez, com a biblioteca fazendo o
  trabalho.
- **Por que foi rejeitada:** é a **Alternativa A do ADR-0035**, já rejeitada lá
  com o argumento que continua valendo: cobra política de *trimming*, decisão
  sobre consumer groups e uma segunda fonte de verdade que pode divergir da
  tabela — para resolver um problema que o banco já resolve, e resolve melhor,
  porque é de lá que o `GET /v1/turns/{id}` (o contrato de recuo) responde. O
  gatilho escrito lá continua não atingido.

### Alternativa C — Timestamp como id

- **O que é:** `id:` é o instante em que o evento aconteceu.
- **Por que foi rejeitada:** dois trechos podem ficar prontos no mesmo
  milissegundo — é exatamente por isso que o ADR-0023 ordena trechos por `index`
  e **não** por `created_at`. Um id que não é único não é id. E o `feedback`, que
  não é persistido, não teria timestamp nenhum a oferecer.

## Consequências

**Positivas**

- A retomada não precisa de estado novo em lugar nenhum: o servidor a deriva do
  `Turn`, que já é durável. O ADR-0035 item 3 é cumprido literalmente.
- O id é legível em log e em `curl` (`chunk:2` diz o que é), o que torna a
  depuração de "o aluno pulou uma frase" uma leitura em vez de uma correlação.
- A ordem total vive numa função pura testável em milissegundos, sem canal, sem
  banco e sem event loop.

**Negativas — o preço aceito**

- **O servidor precisa conhecer a ordem dos eventos**, e essa ordem é a do
  pipeline atual. Se o worker um dia publicar `feedback` **antes** do último
  trecho (o que o ADR-0022 não proíbe — a ordem dos campos do professor é
  contrato, a ordem de publicação não), a função de posição passa a mentir e a
  retomada descarta eventos válidos. **Gatilho para revisitar:** qualquer
  mudança na ordem de publicação em `process_turn.py`. É a dependência mais
  frágil desta decisão.
- ~~**O `feedback` continua sendo o buraco**~~ — **fechado em 2026-08-26 pelo
  ADR-0050.** Ele durou três dias e três cards, e o mecanismo que o fechou foi o
  próprio teste que afirmava a ausência: quando o CARD-013 persistiu as
  correções, ele ficou vermelho. Dívida declarada com gatilho escrito **e**
  verificada por teste é dívida que cobra a si mesma.
- **A deduplicação é responsabilidade do servidor**, com um conjunto de ids por
  stream aberto. É memória O(nº de eventos do turn) por conexão — irrelevante
  para 3 a 6 trechos, e uma conta a refazer se um turn passar a ter centenas de
  eventos.
- **Não há como o cliente pedir "do começo" explicitamente** sem omitir o
  cabeçalho, porque não existe id sentinela. Aceito: é exatamente o que o
  `EventSource` faz numa conexão nova.

**Equivalente mental .NET:** é a diferença entre um cursor opaco de servidor
(um `ContinuationToken` que o cliente devolve e só o servidor entende) e uma
chave natural composta que qualquer lado consegue recalcular do agregado. A
escolha aqui é a segunda, porque o agregado já é a fonte da verdade e um cursor
opaco exigiria guardá-lo em algum lugar.
