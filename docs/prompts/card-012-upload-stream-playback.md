# Prompt — CARD-012: a fatia fecha, e pela primeira vez o número é o que o aluno sente

- **Tipo:** prompt de sessão, complemento de `/executa-card 012`
- **Escrito em:** 2026-08-25, no fechamento do CARD-011 (PR #16)
- **Status:** não executado

> **Este prompt não substitui o `/executa-card`.** Aquele comando carrega o
> protocolo (branch, ordem de leitura, premissas antes do plano, DoD item a
> item, convenção de commit). **Rode `/executa-card 012` e leia isto junto** —
> aqui está o que é específico deste card, a arqueologia já feita, **o que o
> CARD-011 já resolveu e o card ainda pede** (§3.2), e as armadilhas que custam
> um card inteiro se descobertas tarde.

---

## 0. Antes do plano: a fila está em onze, e o item está vermelho há sete sessões

`docs/perguntas-em-aberto.md` tem **11 perguntas abertas**. Q5 e Q6 foram
dispensadas; as outras nunca tiveram desfecho.

Reapresente **três** — e desta vez elas tocam o card de verdade, não por
paralelo:

| # | Pergunta | Por que é deste card |
|---|---|---|
| **Q14** | Lendo `response.body` do SSE com o **`fetch` global do RN**: chega em pedaços, chega inteiro no fim, ou dá erro? | Nasceu no CARD-011 e **este é o card que a consome**. A resposta medida é *"em pedaços"* (5 leituras, `chunk 0` em 1,65 s) — e é sobre essa medição que o transporte inteiro deste card se apoia |
| **Q13** | O gerador assíncrono não emite `SUBSCRIBE` antes do primeiro `__anext__`; se o caso de uso lê o banco nessa janela e o worker publica `chunk:0` — o que o aluno vê, e o que acontece com esse trecho? | É a **mesma janela**, agora do lado do cliente: entre abrir o stream e começar a consumir. O CARD-010 a fechou no servidor; este card decide se o cliente a reabre |
| **Q7** | O que `Protocol` faz que dispensa um framework de mock, e **em que momento** se descobre que um fake não satisfaz a porta? | O client de `packages/api-client` é a primeira **porta do lado TypeScript**, e o `tsc --strict` já está de pé (ADR-0043). A pergunta gêmea — *"quando se descobre que o dublê não satisfaz o contrato?"* — agora tem as duas metades no mesmo repositório |

> **É a sétima sessão seguida em que o item da DoD fecha vermelho.** A proposta
> de postmortem sobre a **regra** foi feita no CARD-009 e repetida no 010 e no
> 011, sem resposta nas três. **Abra esta sessão cobrando essa decisão antes de
> qualquer pergunta nova**, e ofereça os três caminhos por escrito (manter e
> responder / reescrever a regra / manter e aceitar o vermelho como dívida
> declarada). Uma regra da constituição que nunca fecha verde não governa nada,
> e reescrevê-la é decisão do desenvolvedor.

---

## 1. Por que este é o próximo card

É **o último card do caminho crítico** (`018 → 006 → 007 → 008 → 009 → 010 →
011 → 012`) e o **critério de saída da Fase 1**.

Todos os números do projeto até aqui são de componentes ou do pipeline do
servidor. A `medicao-latencia.md` §10 mediu a composição **dentro do worker** —
1,56–1,61 s até o primeiro trecho gravado, com storage e repositório em memória.
O que **nunca** foi medido é o que sobra por fora: upload do cliente, pickup da
fila, transporte, download do trecho, decodificação e início do playback.

**Este card produz o primeiro número honesto do produto** — do dedo saindo do
botão até a primeira palavra sair do alto-falante.

---

## 2. O que já está decidido e não se rediscute

- [**ADR-0026**](../adr/0026-entrega-progressiva-por-sse-com-polling-como-contrato-de-recuo.md)
  — SSE é o caminho principal; **`GET /v1/turns/{id}` é o contrato de recuo e
  precisa continuar funcionando**. Os dois caminhos, ambos exercitados.
- [**ADR-0041**](../adr/0041-id-estruturado-do-evento-sse-e-retomada-derivada-do-banco.md)
  — `id` estruturado (`transcribed`, `chunk:{i}`, `feedback`, `completed`,
  `failed`), retomada por `Last-Event-ID` derivada do banco, **dedup por id**,
  e `feedback` **não volta** na retomada.
- [**ADR-0023**](../adr/0023-ciclo-de-vida-do-turn-com-entrega-em-cascata.md) — a
  ordem é `transcribed → chunk:0..n → feedback → completed|failed`. **O áudio
  vem antes do texto do feedback.** `delivered_partially` é derivado.
- [**ADR-0024**](../adr/0024-midia-por-trecho-chave-url-assinada-e-retencao-assimetrica.md)
  — URL assinada viaja no evento, **TTL curto**; trecho expirado com `full`
  presente ⇒ toca o inteiro; ambos expirados ⇒ áudio indisponível, texto
  preservado, **nunca 500**.
- [**ADR-0042**](../adr/0042-idempotencia-do-post-por-coluna-no-postgres.md) — a
  idempotência do `POST` já existe no servidor, por coluna com índice único.
- [**ADR-0008**](../adr/0008-contrato-api-versionamento-e-tipos-gerados.md) — só
  `packages/api-client`, com tipos gerados. Nunca URL ou tipo à mão.
- [**ADR-0043**](../adr/0043-quality-gates-do-cliente-typescript-com-biome.md) —
  os gates do cliente **já existem**: `pnpm run gates`. Nada nasce fora deles.
- [**ADR-0044**](../adr/0044-dependencias-de-arranque-do-app-expo-e-convivencia-com-pnpm.md)
  — as dependências do app e o que **não** entrou, com gatilho.
- **ADR-0002 / ADR-0010** — Expo Go, sem dev build, custo zero.

---

## 3. Arqueologia — verificada no repositório em 2026-08-25

### 3.1 O que existe

- **O app roda.** `apps/mobile` com Expo SDK 57, `expo-router`, `expo-audio`.
  Tela de conversa com permissão (3 estados), gravação com limite que para
  sozinha e informa, playback local e `regravar`. Tudo verificado no Simulador.
- **Os gates do cliente existem e mordem** (ADR-0043): `pnpm run gates` =
  `biome check` + `tsc --noEmit` strict, nos três anéis.
- **O backend entrega.** `/v1/sessions`, `POST /v1/sessions/{id}/turns`,
  `GET /v1/turns/{id}`, `GET /v1/turns/{id}/events`. Confirmado ponta a ponta
  nesta máquina.
- **Os tipos estão commitados**: `packages/api-client/src/schema.d.ts`, e
  `apps/mobile/src/api/contrato.ts` já os consome (`Turn`, `TurnAceito`,
  `Sessao`, `Trecho`, `EtapaDoTurn`).

### 3.2 **Quatro coisas que o texto do card pede e que já estão resolvidas**

Leia esta tabela **antes de planejar**, ou você vai gastar meio card refazendo
o que a sessão anterior mediu.

| O card diz | A realidade em 2026-08-25 |
|---|---|
| *"decidir entre `react-native-sse` e o `fetch` com streaming, sem sair do Expo Go"* — e lista isso como **risco** | **Decidido e medido** (ADR-0044). O `fetch` **global do RN** entrega o `text/event-stream` progressivamente dentro do Expo Go: `transcribed` +686 ms, `chunk 0` **+1653 ms**, `chunk 1` +2782 ms, `feedback` +2788 ms, `completed` +2867 ms, em **5 leituras**. `fetch` aceita `Authorization`, que era o limite do `EventSource`. **Nenhum polyfill entra. Não é preciso dev build.** O risco do card está morto |
| *"Client em `packages/api-client`"* | O pacote tem **só tipos**. O client HTTP (baseURL, `Idempotency-Key`, retry) **não existe** — é deste card, e é a primeira coisa a nascer |
| *"upload ... com `Idempotency-Key`"* | O **servidor** já é idempotente (ADR-0042). O que falta é o cliente **gerar a chave uma vez e reusá-la no retry** |
| *"UI progressiva ... a ordem mudou por causa do ADR-0022"* | A tela do CARD-011 **não** tem lista de turns, de propósito, exatamente para não nascer na ordem errada. Você a monta aqui, na ordem da cascata |

**Há um spike para apagar:** `apps/mobile/app/spike-sse.tsx` é descartável e
sai neste card — ou vira o teste de fumaça dele. Não deixe os dois.

### 3.3 A restrição de operação que muda como esta sessão presta contas

**O agente não consegue tocar na tela do Simulador** — `osascript` está sem
acesso assistivo nesta máquina, conferido no CARD-011. Consequências:

- capturas de tela o agente tira sozinho (`xcrun simctl io booted screenshot`);
- **qualquer toque depende do desenvolvedor**;
- o contorno que funcionou foi **deep link**:
  `xcrun simctl openurl booted "exp://127.0.0.1:8081/--/rota?param=valor&auto=1"`,
  com a tela disparando o fluxo sozinha quando o parâmetro chega. **Use isso de
  novo** — uma rota de medição que roda o ciclo inteiro sem toque é o que torna
  a métrica repetível.

Se o desenvolvedor conceder acesso assistivo ao terminal, a automação de toque
passa a existir. **É decisão dele; não peça de forma implícita.**

### 3.4 O que o CARD-011 deixou pendente e este card fecha de graça

**Permissão negada permanentemente + microfone real, em aparelho físico.** É o
único critério de aceite do 011 ainda aberto. Este card **exige aparelho
físico** para a medição de qualquer forma — feche os dois na mesma ida.

---

## 4. As armadilhas — o que o texto do card não antecipa

### 4.1 A URL assinada aponta para `localhost` — e o aparelho físico não é o Mac

**Esta é a armadilha mais cara desta sessão, e ela é invisível no Simulador.**

`backend/config.py` tem `s3_endpoint_url: str = "http://localhost:9000"`, e é
com esse host que o MinIO **assina** as URLs. Os eventos do spike vieram assim:

```
"url":"http://localhost:9000/voicecoach-media/…/reply/000.aac?X-Amz-Algorithm=…"
```

No Simulador isso funciona (ele compartilha a rede do Mac). **No aparelho
físico, `localhost` é o próprio telefone** — o download do trecho falha, e o
sintoma vai parecer "o playback não funciona", não "a URL está errada".

O mesmo vale para `apiBaseUrl` em `app.json > extra`, hoje
`http://localhost:8000`.

E há uma segunda camada: **a assinatura cobre o host**. Trocar o host da URL
depois de assinada **invalida a assinatura** — não dá para consertar no cliente.
A correção é o servidor assinar com um endpoint alcançável.

**Decida isto no plano, não na hora:** um `s3_public_endpoint_url` em `Settings`
(o host que o cliente usa, separado do que o worker usa para falar com o MinIO)
é a saída provável — e mexer em `Settings` e no formato do que a API entrega
**é ADR** (critério 2, fronteira).

> Some a isso o **ATS do iOS**: tráfego HTTP em claro para um IP da rede local
> pode ser bloqueado. Se aparecer, é achado do card — não motivo para dev build.

### 4.2 Dedup por id não é otimização, é o que evita o professor repetindo frases

ADR-0041 item 3, escrito com todas as letras: o histórico (do banco) e o canal
ao vivo **podem entregar o mesmo evento**. O consumidor guarda os ids já
emitidos e descarta repetição.

Sem isso, o modo de falha é o aluno **ouvindo a mesma frase duas vezes** — e é
intermitente, porque depende de o worker publicar exatamente na janela entre a
leitura do banco e o início do consumo. É a **Q13 do lado do cliente**.

E dois detalhes do mesmo ADR que quebram suposições naturais:

- **`Last-Event-ID` fora do esquema é 400**, não "comece do começo". Não invente
  um id; use o último que você recebeu, ou nenhum.
- **`feedback` não volta na retomada.** Uma UI que reconecte e **espere** o
  feedback para sair do estado de carregamento trava para sempre.

### 4.3 A ordem de playback é o `index`, nunca a ordem de chegada

ADR-0023 item 2: a ordenação é por `index`, **não** por timestamp — "o instante
de criação é medição, a ordem é contrato de playback".

E cuidado com o mesmo bug que o ADR-0041 evitou no servidor: `chunk:10` vem
**depois** de `chunk:2`, e comparação de string diz o contrário.

### 4.4 O gap entre trechos: prefetch é requisito, não polimento

Critério de aceite: **< 150 ms** entre trechos. Isso não sai por acaso — o
trecho N+1 precisa estar **baixado e decodificado** antes de o N terminar, e o
card já avisa que a decodificação no RN tem latência própria **não medida**.

Duas consequências práticas:

- `expo-audio` tocando direto de URL remota embute o download no caminho
  crítico. **Baixar antes** (para o sistema de arquivos) é o que dá controle —
  e é uma decisão com custo, então decida no plano.
- Herança do CARD-011: no iOS, `setAudioModeAsync({ allowsRecording: true })`
  joga o playback para o alto-falante do ouvido. **Desligue `allowsRecording`
  antes de tocar** — já está feito em `useGravacao`, não desfaça.

### 4.5 A `Idempotency-Key` é gerada uma vez, na gravação — não por tentativa

O card diz "gerada ao concluir a gravação (o retry reusa a mesma chave)", e essa
parte entre parênteses é o requisito inteiro. Chave gerada dentro da função de
envio = uma chave por tentativa = **turn duplicado por retry**, que é
exatamente o que o ADR-0042 existe para impedir.

O critério de aceite pede a prova: falha de rede, retry com a mesma chave,
**nenhum turn duplicado**. O `TurnAcceptedResponse` tem `replayed: boolean` —
**use-o como evidência**, é ele que diz que o servidor reconheceu a repetição.

### 4.6 O recuo que ninguém testa apodrece

ADR-0026 item 4 e o critério de aceite: com o stream indisponível, o app cai
para polling **e o turn completa**. O card manda testar "com SSE desligado por
flag" — então a flag **é escopo**, não conveniência.

Um app que só saiba consumir SSE torna o `GET /v1/turns/{id}` um endpoint morto
que o CI acha que funciona.

### 4.7 Medir "primeiro áudio audível" é mais difícil do que parece

O alvo do card é **≤ 2,4 s p50**, com quatro marcos separados: `parei de falar →
upload completo → primeiro chunk recebido → primeiro áudio audível`.

O quarto marco é o traiçoeiro: `player.play()` **retornar** não é o som saindo
do alto-falante. Use o status do player (o instante em que `playing` vira
verdadeiro, ou `currentTime` sai de zero) e **escreva no card qual marco você
usou** — um número sem método declarado é anedota (`medicao-latencia.md`).

E `p50` implica **repetição**: uma execução não tem mediana. Planeje N ≥ 10, e é
aí que a rota disparada por deep link (§3.3) paga o investimento.

---

## 5. Escopo — o que corta se estourar

- **Não corte:** a medição ponta a ponta com os quatro marcos (é o critério de
  saída da fase), o recuo por polling, a dedup por id, e a ordem por `index`.
- **Pode virar card próprio:** a UI rica de correções (já é CARD-016), o
  tratamento de offline real (já está **Out**), a animação de transição entre
  estados.
- **Se o gap de 150 ms não for atingido:** **não** esconda. Meça, escreva o
  número real e o que dominou o tempo (download? decodificação?). Um número ruim
  medido vale mais que um critério verde por omissão — foi assim que o
  ADR-0021 nasceu.

---

## 6. Governança

1. **Item de ADR da DoD** — confira contra `docs/adr/README.md` e **cite o
   critério** (LEARNING-0003). Candidatos já visíveis:
   - **critério 2** — o endpoint público das URLs assinadas (§4.1): muda
     `Settings` e o que a API entrega ao cliente;
   - **critério 2** — a forma do client de `packages/api-client` (é uma
     fronteira nova: quem monta URL, quem trata retry, quem guarda a chave);
   - **critério 1** — qualquer dependência nova (e a régua está alta: o
     transporte **não** precisa de nenhuma);
   - **critério 5** — a estratégia de prefetch/fila de playback, se ela ficar
     acoplada à UI.
2. **A skill `voicecoach-cliente` é de consulta obrigatória** e **cresce nesta
   sessão**: ela já tem as regras de contrato, transporte, URL expirada e
   design. Regra que não bater com o código é ADR novo ou bug — nunca
   afrouxamento em silêncio. Log de decisões no `REFERENCE.md`.
3. **Decisão que os ADRs não cobrem vai ao desenvolvedor ANTES da primeira linha
   de código.** Nesta sessão são pelo menos três: o endpoint público do storage
   (§4.1), a forma do client, e onde mora a fila de playback.

---

## 7. Definition of Done específica deste card

Além da DoD do `CLAUDE.md` (backend) e dos gates do cliente (`pnpm run gates`):

- [ ] **O número existe, medido no aparelho físico, com N ≥ 10 e p50 escrito** —
      com os quatro marcos separados e o método declarado (§4.7). **É o critério
      de saída da Fase 1.**
- [ ] **Gap entre trechos medido** e comparado aos 150 ms. Se não atingir, o
      número real e a causa dominante estão escritos.
- [ ] **Ordem por `index` provada**, inclusive com um turn de ≥ 10 trechos ou
      com o teste que force chegada fora de ordem.
- [ ] **Dedup por id provada**: reconectar no meio de um turn **não** reproduz
      áudio já ouvido (ADR-0041 item 3).
- [ ] **Background por 5 s e volta**: retoma do último evento, sem repetir.
- [ ] **Recuo por polling exercitado com o SSE desligado por flag**, e o turn
      completa.
- [ ] **Retry com a mesma `Idempotency-Key` não duplica turn** — evidência com
      `replayed: true` na resposta.
- [ ] **Falha depois de 2 trechos**: a UI diz o que aconteceu **sem apagar o que
      já foi ouvido** (a invariante do ADR-0023 item 6, agora visível na tela).
- [ ] **URL de trecho expirada** tratada: repedir o GET; `full` presente ⇒ toca o
      inteiro; ambos ausentes ⇒ texto preservado, **nunca** tela de erro fatal.
- [ ] **A tela reflete a ordem da cascata** — áudio primeiro, feedback depois —
      e a divergência com o artboard 05 continua registrada.
- [ ] **`spike-sse.tsx` saiu do repositório** (ou virou o teste de fumaça).
- [ ] **Pendência do CARD-011 fechada na mesma ida:** permissão negada
      permanentemente, em aparelho físico.
- [ ] Q14, Q13 e Q7 reapresentadas na abertura, com desfecho registrado
      (respondida / dispensada / em aberto). **Item fechado pelo agente com a
      própria explicação não conta** (LEARNING-0004) — e cobre a decisão sobre o
      postmortem da regra (§0).
- [ ] Card atualizado e `docs/backlog/README.md` atualizado. **Se o número sair,
      a Fase 1 fecha** — diga isso explicitamente no card.

---

## 8. Restrições

- **Branch própria** a partir de `main` (com o CARD-011 mergeado — PR #16).
  `main` é protegida. **Confira `git branch --show-current` depois de criar a
  branch**: no CARD-011 dois commits caíram em `main` apesar de o `git switch
  -c` ter reportado sucesso.
- Commit **nunca** leva trailer `Co-Authored-By`
  ([LEARNING-0001](../learnings/0001-commit-com-coautoria-indesejada-do-agente.md)).
- **Não pushe nem abra PR sem perguntar.**
- **Custo:** este card gasta o de sempre em LLM real por turn medido (~US$ 0,02
  por execução do pipeline com `claude-haiku-4-5`). Com N ≥ 10, isso é ~US$ 0,20
  — **declare o total no card** (ADR-0010).

### Como subir o ambiente inteiro (conferido no CARD-011)

```bash
docker compose up -d
cd backend && uv run alembic upgrade head          # a migration do CARD-010
(cd backend && uv run uvicorn voicecoach.api.app:create_app --factory --host 0.0.0.0 --port 8000 &)
(cd backend && uv run voicecoach-worker &)
cd apps/mobile && pnpm expo start                  # QR code para o aparelho
```

> `--host 0.0.0.0` **importa**: sem isso o aparelho físico não alcança a API.
> E lembre da §4.1 — o `apiBaseUrl` e o endpoint do storage precisam ser
> alcançáveis a partir do telefone, não do Mac.

### O display mobile — requisito de sessão, não sugestão

O desenvolvedor **quer ver o app enquanto ele é construído**. É como esta sessão
presta contas.

1. Simulador rodando durante a sessão para acompanhar:
   `xcrun simctl boot "iPhone 17 Pro" && open -a Simulator`
2. **Mande a captura a cada estado novo** (`xcrun simctl io booted screenshot`),
   não só no fim — e lembre que **toques dependem do desenvolvedor** (§3.3).
3. O que fecha os critérios de **latência, gap e permissão negada** é o
   **aparelho físico**. O Simulador é para acompanhar; o aparelho é para aceitar.
4. Estado que se demonstra melhor em movimento (playback encadeado, o gap entre
   trechos) vai em vídeo: `xcrun simctl io booted recordVideo /tmp/estado.mp4`.

- Responda em português. O desenvolvedor **sabe React** e está na segunda sessão
  de React Native. Ao citar biblioteca, diga qual, por que ela e não a
  alternativa. Pare e explique em 3 linhas o que **não** tem paralelo no React
  web — em especial: `AbortController` numa máquina de estados que sobrevive à
  troca de tela; o `AppState` (background/foreground) como evento real, e não a
  ficção que a web tem; e o sistema de arquivos do aparelho como lugar onde
  bytes ficam entre o download e o playback. **Sem aula de React, de hooks ou de
  componentes.**
