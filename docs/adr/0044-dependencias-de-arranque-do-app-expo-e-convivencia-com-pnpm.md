# ADR-0044 — As dependências de arranque do app Expo, e a convivência do Metro com o pnpm

- **Status:** aceito
- **Data:** 2026-08-24
- **Complementa:** [ADR-0002](0002-stack-de-cliente-expo-mais-web-separada.md)
  (Expo + RN + monorepo pnpm), [ADR-0026](0026-entrega-progressiva-por-sse-com-polling-como-contrato-de-recuo.md)
  (transporte), [ADR-0010](0010-politica-de-custo-projeto-pessoal.md), visão §F
- **Critérios de obrigatoriedade** (`docs/adr/README.md`): **1 — introduz
  dependências externas** (`expo-router`, `expo-audio`, `react-native-screens`,
  `react-native-safe-area-context`, `expo-linking`, `expo-constants`). O
  critério **2** (fronteira: resolução de módulos do repositório inteiro) foi
  **avaliado e não se aplicou** — ver §2, e é justamente esse "não se aplicou"
  que valia medir.

## Contexto

O CARD-011 fez o bootstrap de `apps/mobile`, que até então eram dois arquivos
`README.md`. Três decisões precisavam ser tomadas e nenhum ADR as cobria: quais
dependências entram no dia 1, se o `expo-router` se justifica com **uma** tela, e
o que o Metro exige para funcionar dentro de um workspace pnpm.

A terceira era a de maior alcance. O `create-expo-app` assume `npm`/`yarn` com
`node_modules` achatado; o pnpm instala uma store com **symlinks**, e o Metro
resolve módulos por caminho de arquivo. A receita que circula é criar um
`.npmrc` com `node-linker=hoisted` — o que mudaria a resolução de módulos do
**repositório inteiro**, não só do app.

## Decisão

### 1. As dependências de arranque, e por que cada uma

| Dependência | Por quê ela | Alternativa descartada |
|---|---|---|
| `expo` 57, `react-native` 0.86, `react` 19.2 | ADR-0002 | — |
| **`expo-audio`** `~57.0.4` | gravação e playback. O ADR-0002 já a nomeia | **`expo-av`** — está **descontinuado** em favor de `expo-audio` + `expo-video`, e a maioria esmagadora dos tutoriais ainda é dele. **A API é diferente, não é renomeação:** um `Audio.Recording` do `expo-av` num projeto `expo-audio` falha de um jeito que parece bug de permissão |
| **`expo-router`** `~57.0.15` | ver §3 | navegação manual por estado |
| `react-native-screens`, `react-native-safe-area-context` | peers obrigatórios do `expo-router` | — |
| `expo-linking` | deep link; é o que torna o `scheme` utilizável | — |
| `expo-constants` | ler `app.json > extra` (o limite de gravação — ADR abaixo) | constante no código, recusada: o limite é regra de produto |
| `@voicecoach/api-client` (workspace) | ADR-0008: o app só fala com o backend por aqui | tipos à mão |

**O que NÃO entrou, e o gatilho de cada um:**

- **`react-native-sse` e qualquer polyfill de `EventSource`.** O spike do
  CARD-011 mediu, dentro do Expo Go, contra o endpoint real: o **`fetch` global
  do React Native entrega o `text/event-stream` progressivamente** —
  `transcribed` +686 ms, `chunk 0` **+1653 ms**, `chunk 1` +2782 ms, `feedback`
  +2788 ms, `completed` +2867 ms, em 5 leituras do stream. `expo/fetch` também
  funciona. Como `fetch` aceita cabeçalho `Authorization` — que era exatamente o
  limite do `EventSource` citado no ADR-0026 —, **nenhuma dependência de
  transporte é necessária**. *Gatilho para reabrir:* precisar de reconexão
  automática com `Last-Event-ID` sem escrevê-la à mão.
- **Biblioteca de estado global** (Redux, Zustand, Jotai). Não há estado
  compartilhado entre telas — há uma tela. *Gatilho:* a segunda tela que precise
  ler o mesmo estado da primeira.
- **Biblioteca de animação** (`reanimated`). O pulso do botão é uma escala em
  loop, e o `Animated` do próprio RN faz isso com `useNativeDriver`. *Gatilho:*
  gesto contínuo dirigido por toque (scrub do player, arrastar para cancelar).
- **`expo-font` + `@expo-google-fonts/instrument-sans`.** A fonte do style guide
  não vem com o Expo e exige carregamento assíncrono com tela de espera. Adiada
  para não competir com o spike e o gate. *Gatilho:* a próxima sessão de UI —
  está registrada como dívida no CARD-011.

### 2. O Metro convive com o pnpm **sem `.npmrc`** — medido, não presumido

Nenhum `.npmrc` foi criado, e **nada precisou ser hoisted**. O primeiro bundle
saiu limpo:

```
iOS Bundled 3488ms node_modules/.pnpm/expo-router@57.0.15_…/node_modules/expo-router/entry.js (1280 modules)
```

O caminho no log é a prova: o Metro resolveu **através da store do pnpm**,
seguindo symlinks. A causa é conhecida — o Metro ganhou suporte a symlinks
(`unstable_enableSymlinks`, hoje default) e o Expo SDK 57 liga
`Expo Autolinking module resolution`, visível na primeira linha do log do
servidor.

**Consequência de governança:** o critério 2 de ADR (fronteira) **não** se
aplicou, porque a resolução de módulos do repositório **não mudou**. Registrar
isso importa tanto quanto registrar uma mudança: a próxima sessão que topar com
um erro de resolução no Metro precisa saber que o `node-linker=hoisted` foi
**considerado e não foi necessário** — e que ligá-lo é uma decisão sobre o
monorepo inteiro, não um ajuste local.

### 3. `expo-router` entra agora, com uma tela

Foi decisão do desenvolvedor, contra a recomendação de adiá-lo. O argumento a
favor: é a convenção default do Expo hoje, evita a migração de `App.tsx` para
`app/index.tsx` depois, e traz deep linking de graça.

**E o deep linking deixou de ser hipotético na mesma sessão:** foi ele que
tornou o spike de SSE executável a partir do terminal
(`exp://…/--/spike-sse?turnId=…&auto=1`), numa máquina em que o agente **não
consegue tocar na tela do Simulador** (o `osascript` está sem acesso assistivo).
Sem roteador não haveria como disparar a prova sem intervenção manual.

O preço pago é real e fica registrado: uma dependência, uma convenção de pastas
(`app/`) e um `_layout.tsx` que existem antes de haver navegação de verdade.

### 4. Configuração do app fica em `app.json > extra`, lida com validação

`limiteGravacaoSegundos: 90` e `apiBaseUrl` moram em `expo.extra`, e
`src/config.ts` os lê por `expo-constants` **validando no import** — falha alto,
no arranque, e não em silêncio no meio de uma gravação.

O limite é **regra de produto**, não conveniência (diagnóstico §7.4: "cliente
mede e limita duração na captura; servidor valida ambos"), e ele tem um par do
outro lado: `max_turn_audio_duration = 120 s` em `backend/config.py`. **O do
cliente é menor de propósito** — os 30 s de folga são o upload que se escolhe
não desperdiçar para o aluno não receber um 413 depois de falar três minutos.

## Alternativas consideradas

### Alternativa A — `.npmrc` com `node-linker=hoisted` preventivamente

- **O que é:** achatar o `node_modules` do repositório para o Metro não ver
  symlink nenhum.
- **Por que foi rejeitada:** muda a resolução de módulos de **todos** os
  pacotes do workspace para resolver um problema que **não se materializou** —
  e um `node_modules` achatado reintroduz exatamente o *phantom dependency* que
  o pnpm existe para evitar (importar o que não está no seu `package.json` e
  funcionar por acidente). *Gatilho para entrar:* um erro de resolução do Metro
  que não se resolva no `metro.config.js`.

### Alternativa B — `expo-av` em vez de `expo-audio`

- **Por que foi rejeitada:** descontinuado. Registrada porque **é o que a
  internet devolve**: qualquer busca por "expo record audio" traz `expo-av`, e o
  código não falha com "biblioteca errada" — falha parecendo problema de
  permissão. Regra: conferir contra a doc da versão do SDK instalado.

### Alternativa C — Sem roteador, `App.tsx` direto

- **O que é:** o app registra um componente; navegação entra quando houver
  segunda tela.
- **Por que foi rejeitada:** foi a recomendação do agente e o desenvolvedor
  decidiu o contrário (§3). Fica registrada porque a razão dela continua válida
  como régua: uma peça sem consumidor é uma peça sem gatilho (visão §F).

### Alternativa D — Template `default` do `create-expo-app`

- **O que é:** o template com tabs, componentes de exemplo e `reset-project`.
- **Por que foi rejeitada:** traz andaime que precisaria ser apagado, e apagar
  andaime gerado é mais caro que escrever as ~20 linhas de `_layout.tsx`. Usamos
  `blank-typescript` e adicionamos o roteador à mão.

## Consequências

**Positivas**

- O app sobe no Simulador em **~3,5 s de bundle**, sem configuração especial de
  monorepo — o custo do pnpm nesta stack, hoje, é **zero**.
- Uma dependência a menos do que o ADR-0026 previa: o transporte de SSE não
  precisa de polyfill, e isso o CARD-012 já herda decidido e medido.
- O limite de gravação é configuração, e a relação dele com o limite do servidor
  está escrita onde alguém a lê antes de mudá-la.

**Negativas — o preço aceito**

- **A convivência Metro↔pnpm está verificada em UM ponto do tempo**, com SDK 57
  e pnpm 11.2.2. Um upgrade de SDK pode reabrir isso; o gatilho está na
  Alternativa A.
- **`expo-router` sem navegação real** é a peça sem gatilho desta sessão (§3), e
  o custo aparece se ela nunca ganhar a segunda tela.
- **O app ainda não tem a fonte do design.** A tipografia usa a do sistema, com
  os tamanhos e pesos corretos — visualmente próximo, não fiel.
- **`app.json > extra` não é validado pelo Expo**, então a validação é escrita à
  mão e precisa ser mantida junto com os campos. É o preço de não ter um
  `pydantic-settings` deste lado (ADR-0013).

**Equivalente mental .NET:** escolher os pacotes NuGet de arranque de um app
MAUI e descobrir que o `Directory.Packages.props` do repositório não precisava
mudar. A diferença é que aqui a resolução de módulos é do **bundler**, não do
compilador — o Metro empacota o que ele consegue achar no sistema de arquivos, e
"achar" depende de como o gerenciador de pacotes montou o `node_modules`.
