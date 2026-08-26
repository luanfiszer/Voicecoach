# ADR-0046 — A forma do client TypeScript, e os eventos do SSE entrando no contrato

- **Status:** aceito
- **Data:** 2026-08-25
- **Completa:** [ADR-0008](0008-contrato-api-versionamento-e-tipos-gerados.md)
  (item 4: *"tipos puros no pacote `packages/api-client`, junto de um client
  `fetch` fino tipado"* — o client nunca existiu até aqui) e
  [ADR-0026](0026-entrega-progressiva-por-sse-com-polling-como-contrato-de-recuo.md)
  (o transporte)
- **Critérios de obrigatoriedade** (`docs/adr/README.md`): **2 — define uma
  fronteira**, duas vezes: (a) o client é a superfície por onde **todo** o
  produto fala com o backend, e quem decide o que ele faz decide o que os apps
  **não** podem fazer sozinhos; (b) os payloads do SSE passam a ser parte do
  OpenAPI, e sob a política aditiva do ADR-0008 isso é compromisso para sempre.
  O critério **1** foi avaliado e **não se aplicou**: nenhuma dependência entrou.

## Contexto

Até o CARD-012, `packages/api-client` tinha **só tipos**. O ADR-0008 prometia um
client fino "junto deles", e ele nunca foi escrito porque não havia consumidor.
O CARD-012 é o primeiro consumidor, e escrevê-lo revelou dois problemas.

**O primeiro é de forma.** Quem monta a URL, quem faz retry, quem guarda a
`Idempotency-Key`, quem decide cair para o polling — nada disso estava decidido,
e cada resposta diferente produz uma fronteira diferente entre o pacote e o app.

**O segundo é mais grave, e é um furo na promessa central do ADR-0008.** Aquele
ADR diz que mudança de contrato quebra os clientes **em build**. Conferido no
schema gerado, **quatro dos cinco payloads do SSE não estavam lá**:

| Evento | No OpenAPI antes deste ADR? |
|---|---|
| `chunk` | **sim** — de carona em `TurnResponse.chunks` |
| `transcribed`, `feedback`, `completed`, `failed` | **não** |

A causa é mecânica: a rota do stream devolve `EventSourceResponse`, que não é
modelo pydantic, então o FastAPI não tinha o que documentar. O efeito prático é
que o consumo do stream — a parte do produto que este card inteiro existe para
construir — teria de ser tipado **à mão**, que é exatamente o drift que o
ADR-0008 foi escrito para impedir, e que a skill `voicecoach-cliente` lista como
proibido por nome.

## Decisão

**O client é uma função-fábrica que devolve um objeto de funções, com `fetch`
injetável; ele conhece HTTP e o contrato, e nada mais. E os cinco payloads do SSE
passam a existir no OpenAPI, por um envelope declarado na rota do stream.**

### 1. `criarCliente({ baseUrl, fetch?, token? })`

Um objeto com quatro funções: `criarSessao`, `enviarTurn`, `obterTurn`,
`acompanharTurn`. O `fetch` entra por parâmetro, então o dublê de teste é um
objeto literal e o `tsc --strict` reprova o que não satisfizer o tipo — o mesmo
mecanismo que o `Protocol` dá no backend, agora do lado TypeScript.

### 2. A `Idempotency-Key` é **parâmetro**, nunca gerada dentro do client

Gerá-la dentro de `enviarTurn` daria **uma chave por tentativa**, e o retry
criaria um turn novo a cada falha de rede — exatamente o que o
[ADR-0042](0042-idempotencia-do-post-por-coluna-no-postgres.md) existe para
impedir. Ela nasce quando a gravação termina e o retry reusa a mesma; o corpo do
multipart é remontado a cada tentativa (um `FormData` consumido não se reenvia),
a chave não.

### 3. O que o client **não** faz

Ele **não** deduplica, **não** decide quando cair para o polling e **não** toca
áudio. Ele entrega eventos e devolve dados. A máquina de estados — dedup por id
(ADR-0041), recuo, reconexão com `Last-Event-ID`, `AppState` — mora no app,
porque depende de ciclo de vida de aplicativo, que é conhecimento de plataforma.
**A régua:** se precisa saber o que é "ir para background", não é deste pacote.

### 4. `enviarTurn` recebe **`Blob`**, não a URI do arquivo

Medido no Expo Go SDK 57, no Simulador, contra o endpoint real:

```
uri+name+type -> ERRO Unsupported FormDataPart implementation
uri só        -> ERRO Unsupported FormDataPart implementation
blob          -> HTTP 202
```

Isso **inverte** o idioma que todo tutorial de React Native ensina
(`formData.append('audio', { uri, name, type })`). Aceitar a URI no client seria
oferecer um caminho que falha em runtime com uma mensagem que não explica nada.
Quem tem uma URI a converte antes, e essa conversão mora no app
(`src/features/turno/arquivoLocal.ts`), com `XMLHttpRequest` — que é a
implementação do próprio RN e lê `file://` com garantia, ao contrário do `fetch`.

### 5. Os payloads do SSE entram no OpenAPI por um envelope

`TurnEventPayloads` reúne os cinco e é declarado como `response_model` da rota do
stream; um `responses` explícito garante que o media type documentado seja
`text/event-stream` e não um `application/json` que mentiria sobre o corpo. O
modelo **não é validado em runtime** — o FastAPI devolve o `Response` direto —,
ele existe para o contrato. A partir daqui, renomear um campo de qualquer evento
quebra o `tsc` do app.

### 6. O que continua **fora** do contrato, e é dívida escrita

O **Problem Details** (ADR-0040) também não está no OpenAPI, pela mesma causa
mecânica: ele sai de exception handlers, não de modelos de rota. O client o lê de
forma tolerante (`title`/`detail`, com fallback quando o corpo não é JSON — um
502 de proxy não é). **Gatilho para fechar:** o primeiro card que precise
distinguir tipos de problema programaticamente, em vez de só exibir a mensagem.

## Alternativas consideradas

### Alternativa A — Classe `ClienteVoicecoach`

- **O que é:** a forma mais próxima do que se escreveria em C#.
- **Por que foi rejeitada:** entrega o mesmo contrato e cobra mais para dublar —
  um fake precisa satisfazer a classe, não só o formato. A fábrica devolve um
  tipo estrutural, e em TypeScript é o tipo estrutural que o compilador verifica
  de graça. Preferência de estilo **não** foi o critério; testabilidade foi.

### Alternativa B — Funções soltas exportadas (`enviarTurn(baseUrl, …)`)

- **O que é:** sem estado, tudo por parâmetro.
- **Por que foi rejeitada:** `baseUrl` e token passam a viajar em toda assinatura
  e em todo componente que chame qualquer coisa — a fronteira se dissolve, e a
  regra *"nunca montar URL fora do pacote"* deixa de ter um lugar onde ser
  cumprida.

### Alternativa C — Escrever os quatro payloads à mão no cliente

- **O que é:** um `type TranscribedPayload = { transcript: string }` no TS.
- **A favor:** cinco minutos, e teria funcionado hoje.
- **Por que foi rejeitada:** é o drift silencioso que o ADR-0008 rejeitou na
  Alternativa A dele, agora na parte do contrato que muda mais. O custo de
  fechar o furo foi ~15 linhas no backend; o custo de não fechá-lo é um bug de
  runtime no aparelho de alguém, meses depois.

### Alternativa D — Gerador de client completo (orval e afins)

- **O que é:** gerar as funções, não só os tipos.
- **Por que foi rejeitada:** continua valendo a Alternativa B do ADR-0008 —
  esconde o `fetch` e o estado que o desenvolvedor quer aprender, e não geraria
  o que este card tem de específico (o consumo do stream, o retry com chave
  reusada). O gatilho escrito lá segue não atingido.

## Consequências

**Positivas**

- A promessa do ADR-0008 passa a ser **verdadeira para o stream inteiro**, e não
  só para o `GET`. É a segunda vez que escrever o primeiro consumidor revela o
  que faltava numa fronteira — a primeira foi o
  [ADR-0036](0036-o-primeiro-consumidor-revela-o-que-faltava-nas-portas.md).
- O `fetch` injetável dá teste sem rede quando o gate de teste do cliente entrar
  (ADR-0043 item 6) — a decisão de hoje não fecha aquela porta.
- O armadilha do multipart fica **medida e escrita** num lugar onde quem for
  usar o client a encontra, em vez de descoberta de novo daqui a três cards.

**Negativas — o preço aceito**

- **Um modelo pydantic que não descreve resposta nenhuma.** `TurnEventPayloads`
  é um envelope de documentação; quem ler a rota sem ler este ADR vai supor que
  o endpoint devolve aquele objeto. O docstring da classe diz que não.
- **A dedup e o recuo ficam de fora do pacote**, então a web companion terá de
  reimplementá-los quando chegar — ou promovê-los, e aí a fronteira se move de
  novo. **Gatilho:** o primeiro card da web que consuma o stream.
- **`Blob` na assinatura empurra trabalho para o app**: ler o arquivo inteiro na
  memória antes de subir. Para ≤ 90 s de áudio (~1 MB) é irrelevante; para vídeo
  ou anexo grande não seria.
- **O Problem Details continua fora do contrato** (item 6), o que deixa metade
  do formato de erro tipado e metade não.

**Equivalente mental .NET:** é um `HttpClient` tipado registrado por
`AddHttpClient<IVoicecoachApi, VoicecoachApi>` com `HttpMessageHandler`
substituível em teste — só que a "interface" é o tipo estrutural do objeto
devolvido, verificado pelo compilador sem herança nenhuma.
