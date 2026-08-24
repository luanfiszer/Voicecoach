# Prompt — CARD-011: o app nasce, e o desconhecido do projeto é a gravação

- **Tipo:** prompt de sessão, complemento de `/executa-card 011`
- **Escrito em:** 2026-08-23, no fechamento do CARD-010 (PR #15)
- **Status:** não executado

> **Este prompt não substitui o `/executa-card`.** Aquele comando carrega o
> protocolo (branch, ordem de leitura, premissas antes do plano, DoD item a
> item, convenção de commit). **Rode `/executa-card 011` e leia isto junto** —
> aqui está o que é específico deste card, a arqueologia já feita, e as
> **cinco coisas que este card decide e que não têm ADR nenhum ainda**.

---

## 0. Antes do plano: a fila do explicador está em dez, e o item está vermelho há seis sessões

`docs/perguntas-em-aberto.md` tem **10 perguntas abertas**. Q5 e Q6 foram
dispensadas pelo desenvolvedor; as outras nunca tiveram desfecho.

**Este card é de front-end, e a fila é toda de backend.** Nenhuma das dez toca o
que se vai escrever aqui — e fingir que tocam para cumprir tabela seria pior do
que dizer isso. Reapresente **duas**, que são as únicas com ligação honesta:

| # | Pergunta | Por que ainda é deste card |
|---|---|---|
| **Q7** | O que `Protocol` faz que dispensa um framework de mock, e **em que momento** se descobre que um fake não satisfaz a porta? | Não pelo Python: pelo **paralelo**. Este card decide se o TypeScript deste repositório roda com `strict` e o que acontece quando o contrato muda. A pergunta gêmea é *"o que quebra, e quando, se o backend renomear um campo?"* — e a resposta agora é verificável, porque os tipos gerados existem |
| **Q1** | Por que o `src/` layout muda o que é exercitado no teste local, e que classe de erro ele revela que a pasta plana esconde? | É a pergunta sobre **fronteira de empacotamento**, e ela reaparece inteira aqui: `apps/mobile` vai consumir `@voicecoach/api-client` por workspace, e o Metro tem uma relação própria com symlink de monorepo |

> **É a sexta sessão seguida em que o item da DoD fecha vermelho**, e a proposta
> de postmortem sobre a REGRA foi feita no CARD-009, repetida no CARD-010, e não
> respondida nas duas. **Abra esta sessão cobrando essa decisão antes de qualquer
> pergunta nova.** Não é sobre esta sessão; é sobre o mecanismo. Uma regra da
> constituição que nunca fecha verde não governa nada — e reescrevê-la é decisão
> do desenvolvedor, não do agente.

---

## 1. Por que este é o próximo card

O CARD-010 fechou o backend da fatia vertical: existe `/v1`, existe SSE, e o
pipeline entrega o primeiro trecho de áudio em **1,6 s**. **Não existe nenhum
cliente.** O caminho crítico é `018 → 006 → 007 → 008 → 009 → 010 → **011** → 012`,
e o 012 — que é onde o alvo de 1,8 s é medido *como o aluno o sente* — não pode
começar sem app.

Este card ataca o que o roadmap chamou de **maior desconhecido do projeto**:
captura de áudio em React Native e o ciclo de permissões de plataforma.

---

## 2. O que já está decidido e não se rediscute

- [**ADR-0002**](../adr/0002-stack-de-cliente-expo-mais-web-separada.md) — Expo +
  React Native + TypeScript, `expo-audio` para gravação e playback, monorepo pnpm
  com `apps/mobile`, `apps/web`, `packages/api-client`. **`react-native-web` foi
  rejeitado explicitamente** (a web é Vite, separada) — não unifique UI.
- [**ADR-0008**](../adr/0008-contrato-api-versionamento-e-tipos-gerados.md) — o
  app fala com o backend **só** por `packages/api-client`, com tipos gerados do
  OpenAPI. Nunca monte URL nem tipo de request à mão.
- [**ADR-0007**](../adr/0007-autenticacao-jwt-refresh-rotativo.md) — token em
  `expo-secure-store`, **nunca** `AsyncStorage`. (Não há auth ainda; a regra
  entra na skill agora para não nascer errado depois.)
- [**ADR-0026**](../adr/0026-entrega-progressiva-por-sse-com-polling-como-contrato-de-recuo.md)
  — o transporte é SSE com polling de recuo. **O que este card deve à decisão é
  um spike**, não a implementação: ver §4.4.
- [**ADR-0010**](../adr/0010-politica-de-custo-projeto-pessoal.md) — custo zero.
  Expo Go, build local, nada de EAS pago, nada de conta nova.
- **Visão §F** — sem peça de infra nova sem gatilho. Vale para o cliente também:
  nada de state manager global, biblioteca de UI ou navegação exótica "porque
  todo projeto RN tem".

---

## 3. Arqueologia — verificada no repositório em 2026-08-23

### 3.1 O que existe hoje em `apps/`

**Nada além de dois `README.md`.** `apps/mobile/README.md` e
`apps/web/README.md` declaram a fronteira e dizem "ainda vazio". Não há
`package.json`, não há `app.json`, não há uma linha de TypeScript em `apps/`.

O workspace pnpm existe e está correto (`pnpm-workspace.yaml`: `apps/*`,
`packages/*`; `packageManager: pnpm@11.2.2`; `engines.node >=26`).

### 3.2 Cinco coisas que este card decide e que **não têm ADR nenhum**

| Decisão | Por que ela é sua, nesta sessão |
|---|---|
| **Os quality gates de TypeScript** | **Não existe nenhum.** Nem lint, nem typecheck, nem teste — conferido no `.github/workflows/ci.yml` (dois jobs: `backend` e `openapi`) e no `.pre-commit-config.yaml` (todos os hooks locais têm `files: ^backend/`). A DoD do `CLAUDE.md` lista cinco comandos, **todos de `backend/`**. Ou este card cria o anel equivalente para o TS, ou o app nasce sem nenhuma barreira — e o ADR-0015 vira uma regra que vale só para metade do repositório |
| **Como o Expo convive com pnpm** | `create-expo-app` assume npm/yarn com `node_modules` achatado. O Metro resolve módulos por caminho de arquivo e tem histórico ruim com os symlinks do pnpm. Pode exigir `.npmrc` com `node-linker=hoisted` — **e não existe `.npmrc` na raiz** (conferido). Isso afeta o repositório inteiro, não só `apps/mobile` |
| **Navegação** | O card diz `expo-router`. Com **uma** tela, ele é uma dependência e uma convenção de pastas para resolver um problema que não existe ainda. Decida — e escreva o porquê, seja qual for |
| **A fonte `Instrument Sans`** | O style guide do design a fixa. Ela não vem com o Expo: exige `expo-font` + `@expo-google-fonts/instrument-sans`, carregamento assíncrono e uma tela de espera até a fonte existir. É dependência e é decisão de arranque |
| **Onde moram as cores e a tipografia** | O design entrega tokens exatos (§3.4). Espalhá-los em `StyleSheet` por componente garante divergência no terceiro componente |

> Pelo menos as duas primeiras acionam o **critério 1** ("introduz dependência
> externa") e a primeira aciona também o **critério 6** ("contraria uma convenção
> estabelecida" — o ADR-0015 descreve três anéis que hoje só cobrem o backend).
> Confira contra `docs/adr/README.md` e **cite o critério** (LEARNING-0003).

### 3.3 O que o CARD-010 deixou pronto e muda este card

1. **O contrato existe, e os tipos também.** O card foi escrito quando o backend
   não tinha rota — dizia *"contrato pode ser mockado até CARD-010"*. Não precisa
   mais: `packages/api-client/src/schema.d.ts` está **commitado e gerado do
   OpenAPI real**, com `package.json` e o script `generate`. O app pode importar
   `@voicecoach/api-client` no primeiro dia.
2. **O backend sobe e responde.** `uv run uvicorn voicecoach.api.app:create_app
   --factory --reload` + `docker compose up -d` + `uv run voicecoach-worker`
   entregam um turn de verdade. **Isso muda o spike de SSE da §4.4**: ele pode
   ser feito contra o endpoint real em vez de um mock — o que é a diferença entre
   "o polyfill importa sem erro" e "o polyfill recebe eventos".
3. **As rotas `/v1` estão abertas** (sem auth, `DEV_STUDENT_ID` implícito). Não
   há token para guardar nesta sessão — o que **não** dispensa a regra do
   `expo-secure-store` de entrar na skill.

### 3.4 O design existe, é detalhado, e está parcialmente desatualizado

`docs/design/` tem o `Design.pdf` e, desde o fechamento do CARD-010, os **17
artboards em PNG** em `docs/design/artboards/`, com índice em
`docs/design/README.md`. **Leia o índice antes do plano** — ele resume o style
guide em texto e registra as divergências.

Os tokens são exatos e não precisam ser inventados:

| Papel | Light | Dark |
|---|---|---|
| fundo | `#F7F5F2` | `#121211` |
| superfície | `#FFFFFF` | `#1A1918` |
| tinta | `#171614` | `#F2F0EC` |
| secundário | `#6E6A62` | — |
| acento | `#B44B31` | `#E4795C` |

Tipografia **Instrument Sans**: Display 30/600 · Correção 19/600 · Corpo 16.5/400
· Apoio 13.5/400 · Rótulo 9.5/600 tracking .16em. Alvo mínimo **48px**; botão de
gravar **84px**, **pulso = gravando**, **quadrado = parar**.

**Duas armadilhas do design, e as duas são caras:**

1. **Não existe artboard do estado "gravando"** — justamente o coração deste
   card. O prompt original pedia (estado `b`, com nível de áudio, tempo decorrido
   e limite visível) e ele não foi entregue. O que existe para derivá-lo é o
   style guide. **Não invente uma tela nova: derive dos tokens e do botão.**
2. **A ordem de entrega desenhada está invertida.** O artboard 05 diz *"Áudio a
   caminho… / Você já pode ler; o áudio toca sozinho quando chegar"*, e o
   artboard 03 diz *"você pode guardar o telefone, avisamos com som"*. Os dois
   descrevem o produto de 17/08, antes da cascata (ADR-0022/0023, de 19/08) e
   antes de o primeiro trecho cair para 1,6 s. **Hoje o áudio vem primeiro**, em
   3–6 trechos, e o texto do feedback fecha depois. Isso é do CARD-012, mas a
   tela que você monta aqui não pode nascer estruturada na ordem errada.

E `reiniciar demo` / `a. idle` no rodapé do artboard 01 são **andaime de
apresentação** — premissa P2 de `docs/reconciliacao-telas-dominio.md`, registrada
lá como *não confirmada*. Não implemente.

### 3.5 O ambiente da máquina, conferido

| Fato | Consequência |
|---|---|
| **iOS Simulator disponível**: iPhone 17 Pro / 17 Pro Max / 17e, iOS 26.5 | É por onde o desenvolvedor vai **acompanhar visualmente** (§8) |
| **Não há emulador Android** (`~/Library/Android/sdk/emulator` ausente) | Android só em aparelho físico, via Expo Go |
| `watchman` **não instalado** | O Metro roda sem ele, com aviso e file watching mais lento. Decida se instala (`brew install watchman`) ou convive — e escreva qual |
| `node 26`, `pnpm 11.2.2` | Alinhados com o `engines` da raiz |
| Nenhum `.npmrc` na raiz | Ver §3.2 |

---

## 4. As armadilhas — o que o texto do card não antecipa

### 4.1 O gate de TypeScript é a decisão estrutural silenciosa desta sessão

É o análogo exato do `lifespan` no CARD-010: a coisa que não existe, que ninguém
sente falta no primeiro dia, e que fica cara depois.

Hoje o repositório tem **três anéis** de qualidade (ADR-0015) e os três só olham
`backend/`. Se o app nascer sem equivalente, a primeira consequência é concreta e
previsível: **o ADR-0008 promete que "mudança de API quebra os clientes em build,
não em runtime"** — e sem `tsc` rodando em lugar nenhum, essa promessa é falsa. O
CI compara o `schema.d.ts` commitado, mas ninguém compila o app contra ele.

O que precisa ser decidido, e é escopo real:

- **typecheck**: `tsc --noEmit` com `strict`? (o backend roda `mypy --strict`; um
  TS frouxo ao lado de um Python estrito é incoerência que alguém vai herdar);
- **lint/format**: ESLint + Prettier, ou **Biome** (uma ferramenta, uma config —
  o argumento que fez o `ruff` ganhar no backend)? Diga qual e por quê **e** a
  alternativa descartada;
- **teste**: entra agora ou tem gatilho escrito? Testar RN exige
  `jest-expo` + `@testing-library/react-native`, que é superfície real. **Não
  tenha vergonha de adiar com gatilho** — só não adie em silêncio;
- **onde roda**: hook do agente, `pre-commit` (que hoje filtra `^backend/`), CI,
  ou os três.

**Cede escopo de UI antes de ceder isto.** Uma tela feia com gate é recuperável;
um app inteiro sem gate é uma refatoração.

### 4.2 `expo-audio` é novo, e a internet vai te dar `expo-av`

`expo-av` está **descontinuado** em favor de `expo-audio` + `expo-video`, e a
esmagadora maioria dos tutoriais, respostas de fórum e exemplos ainda é de
`expo-av`. A API é diferente — não é renomeação. O ADR-0002 diz `expo-audio`.

Consequência prática: **confira contra a documentação da versão do SDK que você
instalou**, não contra memória nem contra o primeiro exemplo que aparecer. Um
`Audio.Recording` do `expo-av` num projeto `expo-audio` falha de formas que
parecem bug de permissão.

### 4.3 O ciclo de permissão tem três estados, não dois, e o design desenhou o terceiro

`concedida` / `negada` / **`negada permanentemente`**. No iOS, depois da primeira
negação o sistema **não pergunta de novo**: chamar `requestPermission()` retorna
negado na hora, sem diálogo. O único caminho é `Linking.openSettings()`.

O design já resolveu isso — artboard 13, com a microcopy pronta: *"Precisamos do
microfone / O app funciona por voz — sem microfone não há aula. Você pode liberar
em Ajustes."* → **Abrir Ajustes** / **Agora não**.

O critério de aceite do card cobre isso (*"negada ⇒ mensagem com caminho para
configurações"*), e é o item que o card manda **nunca** cortar.

> **No Simulador, o microfone é o do Mac** e a permissão se comporta de forma
> diferente da do aparelho. O fluxo de negação **precisa** ser verificado em
> aparelho físico, ou você testou outra coisa.

### 4.4 O spike de SSE: meia hora aqui, ou um card inteiro perdido depois

O ajuste de 19/08 do card acrescentou um requisito que é fácil de ler e pular:
**verificar dentro do Expo Go se o consumo de SSE é viável.**

O motivo está no ADR-0026: o `EventSource` nativo **não aceita cabeçalho
`Authorization`**, então o cliente vai precisar de `react-native-sse` (polyfill
com headers) ou do `fetch` com streaming. Se qualquer um deles exigir **dev
build**, o ADR-0002 é contrariado e o CARD-012 precisa saber disso **antes** de
começar — o recuo escrito é a Alternativa C do ADR-0026 (NDJSON sobre `fetch`
streaming) e, em último caso, polling curto **com o número medido escrito**.

**E agora o spike pode ser honesto**, porque o backend do CARD-010 existe: aponte
para `GET /v1/turns/{id}/events` de verdade. "Importou sem erro" não é resposta;
"recebeu os eventos `chunk` em ordem, dentro do Expo Go" é.

Registre o resultado no card **e** na skill nova, com o número da versão do Expo
Go em que foi testado.

### 4.5 O limite de duração é regra de produto, não conveniência

O card manda gravar com **limite de duração configurável**, e a origem está no
diagnóstico §7.4: o protótipo usava *"cap de 2 MB como proxy de duração"* porque
o servidor não conhecia a duração antes de baixar. O destino escrito é
**"cliente mede e limita duração na captura; servidor valida ambos"**.

**A metade do servidor já existe** (CARD-010): a borda decodifica o upload e
recusa acima de `max_turn_audio_duration`, hoje **120 s**. O app precisa parar
sozinho **antes** disso, ou o aluno grava 3 minutos, espera o upload e recebe um
413. O limite do cliente deve ser menor que o do servidor, e a diferença é o
custo de rede que você escolhe não desperdiçar.

E há um critério de aceite explícito: *"quando atinge o limite, para sozinha **e
informa**"*. Parar em silêncio é meio requisito.

### 4.6 Não implemente o que é de outro card

**Não** faz upload, **não** consome SSE de verdade na tela, **não** toca a
resposta do professor, **não** encadeia trechos — tudo isso é **CARD-012**. **Não**
faz auth (fase própria), **não** faz a UI de correções (CARD-016), **não** faz o
resumo pós-sessão nem o histórico (o design os tem, e eles não são deste card).

O spike da §4.4 é **spike**: prova de viabilidade, com o resultado escrito, não
uma implementação que fica.

**A regra de fronteira é a do `apps/mobile/README.md`:** o app fala com o backend
só por `packages/api-client`, e nada em `apps/*` é importado por `packages/*`.

---

## 5. Escopo — o que corta se estourar

O card é **M** e é a primeira sessão de React Native do desenvolvedor. O card já
escreveu a regra de desempate, e ela é diferente da do backend: **se estourar, o
corte é na UX (estados mínimos), nunca no fluxo de permissão.**

- **Não corte:** o fluxo de permissão com os três estados; o limite de duração
  que para sozinha e informa; a reprodução local do que foi gravado; e o **gate
  de TypeScript** (§4.1).
- **Pode virar card próprio:** a fidelidade visual ao design (dark mode, a fonte
  `Instrument Sans`, o pulso do botão), o `expo-router` se a decisão for adiá-lo,
  e o teste automatizado de RN.
- **O spike de SSE não cede** — ele custa meia hora aqui e um card lá.

---

## 6. Governança

1. **Item de ADR da DoD** (confira contra `docs/adr/README.md` e **cite o
   critério**, LEARNING-0003). Candidatos já visíveis:
   - **critério 1 + 6** — os quality gates de TypeScript (§4.1). É a mais cara da
     sessão e a que o ADR-0015 deixou pela metade sem saber;
   - **critério 1** — o conjunto de dependências de arranque do Expo (`expo-audio`,
     `expo-font`, roteador, fonte) e o que o pnpm exige para o Metro funcionar;
   - **critério 2** — se o `.npmrc` com `node-linker=hoisted` entrar, ele muda a
     resolução de módulos do **repositório inteiro**, não só do app.
2. **A skill `voicecoach-cliente` nasce nesta sessão** — é herança escrita do
   CARD-004, e ela foi adiada **de propósito**: *"regra escrita antes de existir
   tela é letra morta"*. Fontes a destilar: ADR-0002, ADR-0003, ADR-0007,
   ADR-0008, ADR-0024 (URL de trecho expirada) e ADR-0026. Ela nasce com a mesma
   disciplina da irmã: **nenhuma regra sem ADR de origem**, hierarquia de fontes
   no topo, e log de decisões no `REFERENCE.md`.
3. **Decisão que os ADRs não cobrem vai ao desenvolvedor ANTES da primeira linha
   de código.** Nesta sessão são pelo menos quatro: o gate de TS (§4.1), o
   roteador, a estratégia de convivência Expo↔pnpm, e se o teste de RN entra
   agora ou com gatilho.

---

## 7. Definition of Done específica deste card

Além da DoD do `CLAUDE.md` (cujos cinco comandos são de `backend/` — ver §4.1):

- [ ] **O app sobe no Simulador iOS e no aparelho físico**, e o desenvolvedor
      **viu** os dois (§8).
- [ ] **Permissão concedida ⇒ grava; negada ⇒ a tela do artboard 13, com o botão
      que abre os Ajustes de verdade.** Verificado em **aparelho físico** — o
      Simulador não reproduz o estado "negada permanentemente".
- [ ] **A gravação para sozinha no limite e informa** — com o limite vindo de
      configuração, não de constante enterrada, e **menor** que os 120 s que o
      servidor aceita.
- [ ] **Consigo ouvir o que gravei e regravar**, sem sair da tela.
- [ ] **Spike de SSE respondido com evidência**: qual biblioteca, se funciona
      **dentro do Expo Go**, contra o endpoint real do CARD-010, e em que versão
      do Expo Go foi testado. Se exigir dev build, o recuo está escrito.
- [ ] **Existe um gate de TypeScript que roda**, com a saída real colada — e ele
      **morde**: injete um erro de tipo, mostre a quebra, reverta. É o par
      completo que o CARD-006 estabeleceu como padrão de prova.
- [ ] **O app compila contra os tipos gerados** (`@voicecoach/api-client`), mesmo
      sem fazer requisição ainda. É o que torna verdadeira a promessa do ADR-0008.
- [ ] **Tokens do design num lugar só** (paleta, tipografia, alvos de toque), com
      os hex do artboard 17 — não espalhados por `StyleSheet`.
- [ ] **A skill `voicecoach-cliente` existe**, com regra rastreada a ADR.
- [ ] **As divergências do design estão registradas** — em especial que a ordem
      de entrega desenhada está invertida em relação à cascata, e que não existe
      artboard do estado "gravando".
- [ ] Q7 e Q1 reapresentadas na abertura, com desfecho registrado no card
      (respondida / dispensada / em aberto). **Item fechado pelo agente com a
      própria explicação não conta** (LEARNING-0004) — e cobre a decisão sobre o
      postmortem da regra (§0).
- [ ] Card atualizado e tabela de `docs/backlog/README.md` atualizada.

---

## 8. Restrições

- **Branch própria** a partir de `main` (com o CARD-010 mergeado). `main` é
  protegida.
- Commit **nunca** leva trailer `Co-Authored-By`
  ([LEARNING-0001](../learnings/0001-commit-com-coautoria-indesejada-do-agente.md)).
- **Não pushe nem abra PR sem perguntar.** O padrão é o dos PRs #11–#15.

### O display mobile — requisito de sessão, não sugestão

**O desenvolvedor quer ver o app enquanto ele é construído.** Isto não é um
"seria bom": é como esta sessão presta contas, do mesmo jeito que a saída colada
do `pytest` presta contas nas sessões de backend.

A máquina tem **iOS Simulator com iOS 26.5** (iPhone 17 Pro / Pro Max / 17e —
conferido). Portanto:

1. **Suba o Simulador e deixe-o rodando** durante a sessão:

   ```bash
   xcrun simctl boot "iPhone 17 Pro" && open -a Simulator
   cd apps/mobile && pnpm expo start --ios
   ```

2. **Mande a captura ao desenvolvedor a cada estado que ficar pronto** — não só
   no fim:

   ```bash
   xcrun simctl io booted screenshot /tmp/estado.png
   ```

   Use a ferramenta de envio de arquivo para que a imagem apareça na conversa. Um
   estado novo (idle → permissão → gravando → gravado/reproduzindo) é uma captura.

3. **O que o Simulador NÃO prova**, e por isso o aparelho físico continua na DoD:
   o comportamento de permissão negada permanentemente, o microfone real, e a
   latência de captura. O Simulador é para **acompanhar**; o aparelho é para
   **aceitar**.

4. Se algum estado ficar melhor demonstrado em movimento que em foto, grave com
   `xcrun simctl io booted recordVideo /tmp/estado.mp4` e mande o arquivo.

- **Custo:** este card não gasta dinheiro. Expo Go, build local, Simulador —
  nada de EAS pago, nada de conta nova (ADR-0010).
- **Não antecipe o V2** (ADR-0003): sem módulo nativo, sem barge-in, sem áudio
  contínuo. Se `expo-audio` no Expo Go não der conta de gravar, isso é um
  **achado do card** — não um convite a sair para dev build.
- Responda em português. O desenvolvedor **sabe React** e é **iniciante em React
  Native**: a diferença é o ponto do objetivo de aprendizado deste card. Ao citar
  biblioteca, diga qual, por que ela e não a alternativa. Pare e explique em 3
  linhas o que **não** tem paralelo no React web — em especial: `View`/`Text` vs.
  `div`/`span` e por que não existe texto solto; `StyleSheet` sem cascata,
  sem herança e sem unidade; o ciclo de permissão como estado da **plataforma**,
  não do app; e o `AppState` (background/foreground) como coisa que a web só tem
  de mentirinha. **Sem aula de React, de hooks ou de componentes.**
