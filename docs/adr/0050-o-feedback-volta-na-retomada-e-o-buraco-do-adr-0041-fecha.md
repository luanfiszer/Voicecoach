# ADR-0050 — O `feedback` volta na retomada, e o buraco do ADR-0041 fecha

- **Status:** aceito
- **Data:** 2026-08-26
- **Completa:** [ADR-0041](0041-id-estruturado-do-evento-sse-e-retomada-derivada-do-banco.md)
  (item 5, que registrou o gatilho: *"o CARD-013"*),
  [ADR-0035](0035-canal-worker-api-por-pubsub-com-o-banco-como-fonte-da-verdade.md)
  (o banco é a fonte da verdade) e
  [ADR-0026](0026-entrega-progressiva-por-sse-com-polling-como-contrato-de-recuo.md)
- **Depende de:** [ADR-0049](0049-correction-e-entidade-persistida-e-os-campos-texto-viram-derivacao.md)
- **Critérios de obrigatoriedade** (`docs/adr/README.md`): **2 — altera uma
  fronteira**: muda o que a retomada por `Last-Event-ID` entrega ao cliente, que
  é contrato de API sob a política aditiva do ADR-0008.

## Contexto

O ADR-0041 decidiu que a retomada do SSE é **derivada do banco**: o servidor
recalcula do próprio `Turn` os ids já entregues e reemite tudo que vem depois do
`Last-Event-ID`. Cinco eventos, quatro reconstituíveis — e um não:

| Evento | Reconstituível do banco, em 2026-08-23? |
|---|---|
| `transcribed` | sim — `turn.transcript` |
| `chunk` | sim — `turn.audio_chunks` |
| `completed` / `failed` | sim — `turn.status` e os artefatos |
| **`feedback`** | **não** — correção não era persistida |

O item 5 daquele ADR registrou a ausência com todas as letras, e registrou
também o que a reabriria: *"**Gatilho para reabrir:** o CARD-013, que persiste as
correções — a partir dele o `feedback` passa a ser reconstituível e entra no
histórico como os outros."* Havia inclusive um teste afirmando a ausência
(`test_o_historico_nao_reconstroi_feedback`), para que ela fosse verificada em
vez de escrita só em prosa.

O ADR-0049 persistiu as correções. **O gatilho disparou.**

## Decisão

**`historico()` passa a emitir o evento `feedback`, reconstruído de
`turn.corrections`. A condição é `turn.replied_at is not None` — não a existência
de correção.**

1. **A condição é o `replied_at`, e essa é a parte fácil de errar.** Um turn em
   que o aluno não errou nada **teve** o evento `feedback`, com a lista vazia.
   Condicionar a reemissão a `turn.corrections` faria o cliente que reconectasse
   num turn perfeito ficar esperando para sempre um evento que já passou. É a
   diferença entre *"não houve correção"* e *"ainda não chegou"*, e só a primeira
   é representável por uma lista vazia.
2. **O evento interno `FeedbackAvailable` carrega só `corrections`.** Os quatro
   campos texto do payload HTTP não viajam pelo canal: eles são derivados por
   `legacy_summary` (ADR-0049), e mandá-los pelo fio seria transportar a mesma
   verdade duas vezes, abrindo a chance de o evento ao vivo e a retomada
   discordarem — o defeito que o ADR-0028 nomeia.
3. **A montagem do payload HTTP acontece num lugar só**,
   `FeedbackPayload.de_correcoes`, usada pelo caminho ao vivo e pela retomada. Um
   `[0]` escrito na rota daria ao servidor duas implementações da mesma regra.
4. **A posição do `feedback` na ordem total não muda** — continua `(2, 0)`, entre
   os trechos e o desfecho, porque a ordem de publicação do pipeline não mudou
   (`process_turn.py` continua publicando o feedback depois do último trecho).
   O ADR-0041 nomeou essa dependência como "a mais frágil desta decisão"; ela
   segue frágil e segue não violada.
5. **O teste foi invertido, não apagado.** `test_o_historico_nao_reconstroi_feedback`
   virou `test_o_historico_reconstroi_feedback_agora_que_a_correcao_e_persistida`,
   e ganhou dois irmãos: um para o turn sem correção nenhuma e um para o turn
   cujo professor ainda não respondeu. O teste antigo ficar vermelho foi o gate
   funcionando — era exatamente para isso que ele existia.
6. **O `parse_wire` do canal ganha o único caso que não é `**data` direto.**
   `FeedbackAvailable` é o único evento com dataclass aninhada; o `asdict` da
   publicação achatou cada `Correction` num dicionário e cada `StrEnum` na sua
   string, e a volta reconstrói os dois explicitamente. Sem isso o evento
   continuaria comparando **igual** nos testes — um `StrEnum` *é* uma `str` — e
   quebraria só na primeira gravação no banco.

## Alternativas consideradas

### Alternativa A — Manter o `feedback` fora da retomada

- **O que é:** não mexer em nada; o cliente que reconecta continua vendo o
  feedback só no histórico, depois.
- **A favor:** zero trabalho, zero risco de regressão no stream.
- **Por que foi rejeitada:** a ausência era dívida declarada com gatilho
  escrito, não uma decisão de produto. O sintoma é concreto e ruim: o aluno
  perde a conexão no meio do turn, reconecta, ouve o resto do áudio e **nunca vê
  a correção daquele turn** — justamente o dado mais valioso do produto. E a
  razão que sustentava a ausência ("não é reconstituível") deixou de ser verdade.

### Alternativa B — Reemitir o `feedback` só quando houver correção

- **O que é:** condicionar a `turn.corrections` em vez de `turn.replied_at`.
- **A favor:** parece mais econômico — nada de mandar um evento "vazio".
- **Por que foi rejeitada:** é o bug descrito no item 1. O cliente trata
  `feedback` como marco do turn ("o professor terminou de pensar"), e um turn sem
  erro nenhum é o caso **mais comum** — o prompt v2 manda o professor ser
  conservador. A economia é de alguns bytes; o custo é a tela travada no caso
  mais frequente.

### Alternativa C — Persistir o payload do evento inteiro numa coluna JSON

- **O que é:** gravar o `feedback` serializado, e reemitir literalmente o que foi
  publicado.
- **A favor:** a retomada devolve byte a byte o que o cliente perdeu, sem
  derivação nenhuma.
- **Por que foi rejeitada:** é uma segunda fonte de verdade sobre a mesma
  correção, com o agravante de ser opaca ao banco — nenhuma query do CARD-016 ou
  do ErrorPattern conseguiria ler de dentro dela sem parsing. Recria, em forma
  de JSON, exatamente o problema que o ADR-0049 resolveu ao tipar.

## Consequências

**Positivas**

- Os **cinco** eventos do ADR-0026 passam a ser reconstituíveis, e a promessa do
  ADR-0041 ("a retomada é derivada do banco") deixa de ter exceção. É um ADR que
  fecha um item aberto de outro, com o gatilho que ele mesmo escreveu.
- Nenhum estado novo em lugar nenhum: a reemissão sai do `Turn`, que já é
  durável. O ADR-0035 item 3 continua cumprido literalmente.
- O cliente **não muda**: ele já deduplica por id (ADR-0041 item 3), então
  receber `feedback` na retomada é o caso que ele já sabia tratar.

**Negativas — o preço aceito**

- **O histórico do stream ficou maior.** Um turn com duas correções carrega um
  payload de `feedback` de algumas centenas de bytes a mais em cada reconexão.
  Irrelevante hoje; uma conta a refazer se o teto de 2 correções subir.
- **A ordem total continua sendo conhecimento do servidor**, e continua sendo a
  dependência mais frágil herdada do ADR-0041. Se o worker um dia publicar o
  `feedback` **antes** do último trecho — o que o ADR-0022 não proíbe, porque ele
  fixa a ordem dos *campos*, não a das *publicações* —, a função `posicao` passa
  a mentir e a retomada descarta eventos válidos. **Gatilho para revisitar:**
  qualquer mudança na ordem de publicação em `process_turn.py`.
- **O `parse_wire` deixou de ser simétrico.** Quatro eventos são `**data`; um não
  é. A assimetria é pequena e está comentada no código, mas é o primeiro ponto
  onde o formato do fio precisa saber de tipo de domínio — e o próximo evento com
  dataclass aninhada vai pedir a mesma cerimônia.

**Equivalente mental .NET:** é a diferença entre um evento de integração que
carrega o DTO inteiro e um que carrega só a chave, deixando o consumidor
projetar. A escolha aqui é a segunda em relação aos campos legados (derivados na
borda) e a primeira em relação às correções (viajam completas), porque só as
correções são dado; o resto é apresentação de um contrato que está morrendo.
