# CARD-012 — Upload com retry, consumo do stream e playback encadeado (fecha a fatia)

- **ID:** CARD-012 · **Épico:** Fase 1 — Fatia vertical em cascata (fecha a fase)
- **Plataforma:** mobile · **Esforço:** M · **Status:** em execução
- **Dependências:** CARD-010, CARD-011; ADR-0026

## Contexto

O fechamento da fatia vertical, e o único lugar onde o alvo de 1,8 s pode ser
**verificado como o aluno o sente** — do dedo saindo do botão de gravar até a
primeira palavra sair do alto-falante.

## Por que agora

Todos os números do projeto são de componentes isolados. O **custo de composição**
— upload, pickup da fila, transporte, decodificação e início do playback — nunca
foi medido, e a [medição §1](../medicao-latencia.md) diz isso com todas as
letras. Este card é o primeiro número honesto do produto.

## Problema

Dois problemas novos, ambos do cliente:

1. **Consumir SSE em React Native.** O `EventSource` nativo **não aceita
   cabeçalho `Authorization`** — decidir entre `react-native-sse` (polyfill com
   headers) e o `fetch` com streaming do Expo, **sem sair do Expo Go** (a
   restrição do ADR-0002; sair para dev build é custo de V2).
2. **Playback encadeado sem buraco audível.** Tocar 4 arquivos em sequência com
   um gap perceptível entre frases desfaz o ganho: o aluno ouve um professor
   gaguejando. O trecho N+1 precisa estar **baixado e pronto** antes de o N
   terminar.

## Proposta técnica

- Client em `packages/api-client` (tipos gerados do OpenAPI — ADR-0008).
- Upload multipart com `Idempotency-Key` gerada ao concluir a gravação (o retry
  reusa a mesma chave); retry com backoff limitado.
- **Stream como caminho principal, polling como recuo** (ADR-0026): se o stream
  não abrir ou cair sem reconectar, o app cai para `GET /v1/turns/{id}` com
  backoff. Os dois caminhos são exercitados — o recuo que ninguém testa apodrece.
- **Fila de playback**: cada evento `chunk` entra numa fila; o player começa no
  primeiro e faz **prefetch do seguinte** enquanto toca. Métrica: gap entre
  trechos.
- Reconexão com `Last-Event-ID` ao voltar do background.
- URL de trecho expirada ⇒ repedir o GET (ADR-0024).
- **Medição ponta a ponta logada em dev**, com os marcos separados:
  `parei de falar → upload completo → primeiro chunk recebido → primeiro áudio
  audível`. **É este card que diz se 1,8 s foi entregue.**
- UI progressiva: transcrição e correções aparecem quando chegam; o áudio começa
  antes do texto do feedback — a ordem mudou por causa do ADR-0022, e a tela
  precisa refletir isso, não a ordem antiga.

## Escopo

- **In:** client tipado, upload com retry, consumo de SSE com recuo, playback
  encadeado, medição, tratamento de URL expirada.
- **Out:** UI de correções estruturadas (CARD-016); barge-in e realtime (V2);
  offline real.

## Critérios de aceite

- **Dado** uma frase gravada no aparelho físico, **então** ouço a primeira
  palavra da resposta em **≤ 2,4 s p50** medidos no app (o alvo é ~1,8 s; a folga
  é o custo de composição, que este card mede pela primeira vez). **Este é o
  critério de saída da fase.**
- **Dado** 4 trechos, **então** o gap audível entre eles é **< 150 ms** e não há
  reordenação (índice respeitado, não ordem de chegada).
- **Dado** o app em background por 5 s e de volta, **então** a reconexão retoma
  do último evento — sem repetir áudio já tocado.
- **Dado** o stream indisponível, **então** o app cai para polling e o turn
  completa (teste com SSE desligado por flag).
- **Dado** falha de rede no upload, **quando** o retry reenvia com a mesma
  chave, **então** o backend não cria turn duplicado.
- **Dado** um turn que falha depois de 2 trechos, **então** a UI diz o que
  aconteceu **sem** apagar o que já foi ouvido.

## Riscos

- **O polyfill de SSE pode exigir dev build.** Se exigir, o recuo é o `fetch`
  com streaming (Alternativa C do ADR-0026) — e, em último caso, polling curto,
  aceitando o custo de latência **com o número medido escrito no card**, não por
  omissão.
- Decodificar áudio no RN tem latência própria (não medida) que pode dominar o
  gap entre trechos.

## Objetivo de aprendizado

Máquina de estados async na UI de RN com `AbortController`, backoff e o caminho
triste como cidadão de primeira classe; e o consumo de tipos gerados na prática
— mudança de contrato quebra o build do app.

---

## Execução (2026-08-25)

Branch `card-012-upload-stream-playback`. **Status: em execução** — o critério de
saída da Fase 1 **não está fechado** (falta o aparelho físico), e nenhum item foi
marcado como cumprido sem evidência.

### As decisões que foram ao desenvolvedor antes da primeira linha de código

| Decisão | Escolha | Onde ficou registrada |
|---|---|---|
| Branch base (PR #16 estava aberto) | **Mergear o #16 primeiro** | commit `ec8c07d` |
| Host da URL assinada (§4.1 do prompt) | **`s3_public_endpoint_url` em `Settings`** | [ADR-0045](../adr/0045-o-host-que-assina-a-url-e-o-do-leitor-nao-o-do-servidor.md) |
| Forma do client | **Função-fábrica com objeto de funções**, `fetch` injetável | [ADR-0046](../adr/0046-a-forma-do-client-typescript-e-o-contrato-do-sse-no-openapi.md) |
| Onde mora a fila de playback | **Hook próprio em `apps/mobile`** | [ADR-0047](../adr/0047-fila-de-playback-com-um-player-por-trecho-e-a-rota-de-medicao.md) |
| **Payloads do SSE fora do OpenAPI** (achado no meio da sessão) | **Fazer o FastAPI emiti-los** | ADR-0046 §5 |

### Item de ADR da DoD — critérios citados (LEARNING-0003)

Conferido contra a lista "Quando um ADR é OBRIGATÓRIO" de `docs/adr/README.md`:

- **ADR-0045** — critério **2** (altera fronteira: campo novo em `Settings` e
  muda o endereço que a API entrega ao cliente) e critério **4** (privacidade:
  é o endereço por onde a voz do aluno trafega).
- **ADR-0046** — critério **2**, duas vezes: o client é a superfície por onde
  todo o produto fala com o backend, e os payloads do SSE entrando no OpenAPI são
  compromisso aditivo permanente (ADR-0008). O critério **1** foi **avaliado e
  não se aplicou**: nenhuma dependência entrou no pacote.
- **ADR-0047** — critério **1** (`expo-asset`) e critério **5** (a fila é como o
  produto entrega o seu diferencial; trocá-la depois de a UI depender dela custa
  mais que uma sessão).
- **O que NÃO virou ADR, e por quê:** o `updateInterval` de 50 ms, o mapa de
  MIME por extensão e o watchdog de carga são **implementação dentro de decisões
  já tomadas** (ADR-0047 e ADR-0024) — estão documentados no código e no ADR que
  os governa, não em ADR próprio.

### Evidência dos critérios de aceite

| Critério | Estado | Evidência |
|---|---|---|
| **≤ 2,4 s p50** até a primeira palavra | ❌ **não atingido** | **2,47 s** (N=10, Simulador). Tabela completa em [`medicao-latencia.md` §11.2](../medicao-latencia.md). Erra por **70 ms** |
| …no **aparelho físico** | ⏳ **não verificado** | depende do desenvolvedor. **É o critério de saída da Fase 1 e continua aberto** |
| **Gap < 150 ms**, sem reordenação | ✅ | **143 ms p50, 145 ms no pior caso**, n=10. Resolução do instrumento: 50 ms (§11.3) |
| Background 5 s e volta retoma sem repetir | ✅ | app para Ajustes por 6 s e de volta: `concluido sse`, **2 trechos e UM gap** (6.082 ms = o tempo congelado). Um trecho retocado teria produzido transição a mais |
| Recuo por polling com SSE desligado por flag | ✅ | `sseHabilitado: false` ⇒ tela mostra `via = polling` e o turn **completa**: total 4,18 s, gap 444 ms (§11.5) |
| Retry com a mesma chave não duplica turn | ✅ parcial | **servidor provado**: 3 envios com a mesma `Idempotency-Key` ⇒ `replayed: false, true, true`, mesmo `turn_id`, e `select count(*) from turns` = **1**. **O reuso da chave PELO CLIENTE não foi exercitado com falha de rede forçada** — é parâmetro de `enviarTurn` e o laço de retry o reusa, mas isso está provado por leitura, não por execução |
| Falha depois de 2 trechos sem apagar o ouvido | ⏳ **não exercitado** | implementado (`ListaDoTurno` §4 + `delivered_partially`); forçar um `failed` **depois** de trechos exigiria derrubar o MinIO na janela de ~1 s entre o último trecho e a concatenação |
| URL de trecho expirada tratada | ⚠️ **implementado, não disparado** | com `MEDIA_URL_TTL=PT1S` o turn **completou com áudio** (`concluido sse`, gaps 144 ms). É achado do desenho: o player é criado quando o evento chega, então a janela entre assinar e baixar é ~300 ms, e o TTL curto não morde. O caminho de recuperação (watchdog → repedir o `GET` → `full` → áudio indisponível) existe e está tipado, mas **não foi executado** |
| Ordem por `index` com ≥ 10 trechos | ⏳ **não exercitado** | as 10 execuções produziram **2 trechos cada**. A ordenação é numérica (`a.index - b.index`) e a dedup é por índice, mas sem turn longo não há prova |
| Tela reflete a ordem da cascata | ✅ código, ⏳ captura | `ListaDoTurno.tsx` monta transcrição → **áudio** → correção → falha. A captura com um turn real na tela de conversa exige **um toque** (o agente não consegue tocar) |
| `spike-sse.tsx` saiu do repositório | ✅ | `git rm apps/mobile/app/spike-sse.tsx`; virou a rota `/medicao`, que é instrumento e não spike |
| Pendência do CARD-011 (permissão negada permanentemente) | ⏳ **não fechada** | exige aparelho físico |

### O que a sessão descobriu e o card não previa

1. **Quatro dos cinco payloads do SSE não existiam no OpenAPI.** A promessa
   central do ADR-0008 (*"mudança de contrato quebra o cliente em build"*) era
   **falsa justamente para o stream**, porque a rota devolve `EventSourceResponse`
   e não modelo pydantic. Corrigido (ADR-0046 §5); os cinco agora são tipos
   gerados.
2. **`audio/m4a` não está na lista aceita pelo servidor.** O tipo fixo que o
   cliente mandaria dá **415** — `audio/x-m4a` é o nome aceito. Descoberto com um
   415 real, não lendo a lista. O tipo passou a ser derivado da extensão.
3. **O idioma de upload de todo tutorial de React Native não funciona aqui.**
   Medido no Expo Go SDK 57, contra o endpoint real:

   ```
   uri+name+type -> ERRO Unsupported FormDataPart implementation
   uri só        -> ERRO Unsupported FormDataPart implementation
   blob          -> HTTP 202
   ```

   O `enviarTurn` passou a aceitar **só `Blob`**, e a conversão mora no app.
4. **A primeira leva de medição mediu o relógio.** Gap p50 de 594 ms com o
   `updateInterval` no default de 500 ms. Ver §11.3 da medição.
5. **A cauda de latência é do worker.** `process_turn` de 19–22 s com o Anthropic
   respondendo 200. **Causa não isolada** — pendência abaixo.
6. **O Expo Go da App Store não roda este projeto.** Ele está em **54.0.2**
   (publicado em 2025-09-23, SDK 54) nas quatro lojas conferidas; o projeto está
   no SDK 57. Um iPhone físico só instala pela loja, então o caminho previsto
   pelo ADR-0002 **não existe** para este SDK. Virou o [ADR-0048](../adr/0048-o-expo-go-da-loja-ficou-para-tras-e-o-aparelho-fisico-vira-divida.md),
   com as três alternativas investigadas (dev build local, downgrade para o
   SDK 54, TestFlight) e a decisão do desenvolvedor: seguir verificando no Mac.
7. **O terminal desta máquina não alcança a LAN.** `ping` responde, TCP dá
   timeout, firewall desligado: é a permissão **"Rede local"** do macOS, a mesma
   classe do acesso assistivo da §3.3. Não afeta telefone→Mac.

### Regra do explicador — desfecho de cada item (LEARNING-0004)

| Pergunta | Momento | Desfecho |
|---|---|---|
| **P1** — URL assinada para `localhost` com o host trocado para o IP da LAN: o que o MinIO responde? | antes de escrever o `s3_public_endpoint_url`, no ponto da decisão | **1ª resposta errada** ("200 — funciona"). Demonstrado com as três execuções (`localhost` → 200; host trocado → **403 `SignatureDoesNotMatch`**; assinada já para o outro host → 200) e explicado o `X-Amz-SignedHeaders=host`. **Reformulada uma vez** (dois clientes boto3, objeto gravado por um e lido pela URL do outro) e **respondida corretamente**. ✅ **fechada** |
| **P2** — um player por trecho vs. um player com `replace(url)`: qual a consequência observável? | antes de escrever a fila | **respondida corretamente na primeira** ("em (A) o gap contém download+decodificação"). ✅ **fechada** |
| Perguntas seguintes | — | **dispensadas pelo desenvolvedor** (*"pule essas perguntas"*). Registrado como dispensa, **não** como cumprido |
| **Q14, Q13, Q7** (fila de `perguntas-em-aberto.md`) | reapresentadas na abertura, antes do plano | **sem resposta e sem dispensa** — seguem na fila |
| **Decisão sobre a regra** (§0 do prompt, pendência de topo há 7 sessões) | reapresentada na abertura, com os três caminhos por escrito | **sem resposta** — continua sendo a pendência de topo |

### Custo (ADR-0010)

**~40 execuções do pipeline com `claude-haiku-4-5` real**, entre a leva
descartada (instrumento grosso), a leva definitiva (N=10), o recuo por polling, a
idempotência e os testes de background e TTL. A ~US$ 0,02 cada: **≈ US$ 0,80**.

### Dívidas explícitas

| Dívida | Gatilho / card |
|---|---|
| **O número no aparelho físico** — critério de saída da Fase 1 | **bloqueado pelo canal, não por trabalho** ([ADR-0048](../adr/0048-o-expo-go-da-loja-ficou-para-tras-e-o-aparelho-fisico-vira-divida.md)): o Expo Go da App Store está no SDK 54 e o projeto no 57. Saída escolhida e verificada: `npx expo run:ios --device` (Xcode 26.6 e iPhone pareado já existem nesta máquina). Quando for cobrada, `S3_PUBLIC_ENDPOINT_URL` e `apiBaseUrl` apontam para o IP da LAN (ADR-0045) |
| Permissão negada permanentemente (herdada do CARD-011) | mesma ida ao aparelho, mesmo bloqueio |
| **p50 de 2,47 s contra o alvo de 2,4 s** | a cauda do worker (abaixo) é a alavanca mais provável |
| **Cauda de 19–22 s em `process_turn`, causa não isolada** | card próprio; candidatos: recarga do `mlx-whisper`, contenção de GPU, cauda do provedor |
| Ordem por `index` com ≥ 10 trechos, não exercitada | insumo que produza resposta longa |
| Falha depois de 2 trechos, não exercitada | ver acima |
| Recuperação de URL expirada, implementada e não disparada | ver acima |
| Reuso da `Idempotency-Key` pelo cliente, provado por leitura | precisa de falha de rede forçada — depende do gate de teste do cliente (ADR-0043 item 6) |
| **Problem Details fora do OpenAPI** | ADR-0046 §6, com gatilho |
| Dedup e recuo vivem no app, não no pacote | 1º card da web que consuma o stream |
