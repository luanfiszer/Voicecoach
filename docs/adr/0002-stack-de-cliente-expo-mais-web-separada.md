# ADR-0002 — Stack de cliente: Expo/React Native (mobile) + web separada (Vite) em monorepo

- **Status:** aceito
- **Data:** 2026-08-17

## Contexto

O ADR-0001 definiu app mobile como carro-chefe e web como companion. O
desenvolvedor sabe React, nunca publicou app mobile, e o aprendizado de
React/React Native é objetivo de primeira classe. A web companion é
essencialmente um dashboard (gráficos, tabelas, histórico navegável). A
decisão de maior impacto do projeto: quantas bases de código de cliente, e
com qual tecnologia.

## Decisão

1. **Mobile**: Expo (React Native) com TypeScript. Expo Go/dev build para
   desenvolvimento (distribuição por build local — decisão da sessão P2).
2. **Web**: aplicação separada com **Vite + React + TypeScript** — React web
   "de verdade", com o ecossistema web inteiro disponível.
3. **Monorepo pnpm workspaces**: `apps/mobile`, `apps/web`,
   `packages/api-client` (tipos gerados do OpenAPI + client HTTP fino — ver
   ADR-0008).
4. Áudio no mobile via `expo-audio` (gravação AAC/m4a + playback) — suficiente
   para o V1 turn-based; o V2 realtime exigirá dev build com módulo nativo
   (previsto no ADR-0003, não bloqueia esta decisão).

## Alternativas consideradas

### Alternativa A — Expo/React Native cobrindo tudo, incluindo web (react-native-web)
- O que é: uma única base RN renderizando iOS, Android e web.
- Por que foi rejeitada: (1) o valor da web companion está em gráficos ricos e
  tabelas densas — o ecossistema que resolve isso (Recharts/visx, TanStack
  Table, CSS real) é web-nativo e funciona mal ou não funciona sobre RN-web;
  o resultado tende a "site que parece app engessado". (2) Metade do objetivo
  de aprendizado é React **web** — RN-web ensinaria um dialeto (View/Text,
  StyleSheet) em vez de DOM/CSS/ecossistema que entrevistas cobram. (3) A
  sobreposição real entre os clientes é pequena por decisão de produto (§A da
  visão): compartilhar UI renderia pouco.

### Alternativa B — Nativo: Swift (iOS) + Kotlin (Android)
- O que é: dois apps nativos, web à parte.
- Por que foi rejeitada: triplica o currículo (Swift + Kotlin + React web),
  zero reuso do React existente, e o ganho (controle máximo de áudio/UX) não é
  necessário no V1. Gatilho registrado: se o V2 realtime esbarrar em limite
  real dos módulos de áudio do ecossistema RN (latência de captura, echo
  cancellation), reavaliar **módulo nativo pontual** dentro do RN — não app
  nativo inteiro.

### Alternativa C — Flutter
- O que é: Dart + Flutter para mobile (e eventualmente web).
- Por que foi rejeitada: sai do objetivo declarado de aprender React por
  definição. Qualidade da opção é irrelevante diante do critério.

### Sub-decisão: monorepo vs repositórios separados
- Duplicar tipos/client em dois repos garante drift de contrato — exatamente a
  classe de bug que tipos gerados eliminam. O custo do monorepo (pnpm
  workspaces, um lockfile, configuração inicial) é pago uma vez; o custo da
  duplicação é pago a cada mudança de API. Backend Python permanece no mesmo
  repositório (`backend/`), fora dos workspaces pnpm.

## Consequências

**Positivas**
- Currículo completo: React Native real no mobile + React web real no
  dashboard, com TypeScript compartilhado.
- Cada plataforma usa o melhor do seu ecossistema (expo-audio; Recharts/CSS).
- Contrato único via `packages/api-client` — mudança de API quebra os dois
  clientes em build, não em runtime.

**Negativas — o preço aceito**
- Duas bases de UI para manter (navegação, estado, estilo divergem entre RN e
  web). Aceito porque a sobreposição de telas é pequena por decisão de produto.
- Monorepo JS + backend Python no mesmo repo = duas toolchains convivendo
  (pnpm + uv/pip); CI precisa orquestrar ambas.
- Expo impõe seu ciclo de upgrade (SDK releases) — custo recorrente conhecido.

**Equivalente mental .NET:** dois frontends (MAUI + Blazor) consumindo a mesma
API com DTOs gerados de um contrato — a decisão de não unificar UI é a mesma
que se toma ao não forçar Blazor Hybrid em todo lugar.

## Observação de campo (adicionada em 2026-08-17, não altera a decisão)

Durante o CARD-001, o monorepo MEDSoft (empresa do desenvolvedor) foi analisado
como referência. Ele **é** a Alternativa A em produção: Turborepo + pnpm com
`apps/{web(Next.js), mobile(Expo)}` compartilhando UI via `react-native-web`.

O preço dessa escolha está visível no repositório: três pacotes só para
conciliar aparência entre plataformas (`ui`, `ui-override`, `ui-tokens`),
arquivos `.web.tsx`/`.native.tsx` espalhados pelo código compartilhado, e um
`CLAUDE.md` de 24 KB em que seções inteiras são *quirks* de plataforma
("Platform-Specific Files", "Environment quirks", "Responsive / Breakpoints").

Isso não muda a decisão — reforça-a com dado observado em vez de argumento.
O que **foi** aproveitado do MEDSoft está no ADR-0012 (regra arquitetural como
artefato executável). O layout `apps/*` + `packages/*` que eles usam coincide
com o já decidido aqui.
