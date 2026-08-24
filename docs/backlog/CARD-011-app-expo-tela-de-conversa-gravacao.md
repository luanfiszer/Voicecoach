# CARD-011 — App Expo: esqueleto, tela de conversa e gravação de áudio

- **ID:** CARD-011 · **Épico:** Fase 1 — Fatia vertical
- **Plataforma:** mobile · **Esforço:** M · **Status:** em execução — falta só o aparelho físico (2026-08-24)
- **Dependências:** CARD-001 (workspace); contrato pode ser mockado até CARD-010

## Contexto

ADR-0002 (Expo + TS no monorepo). Primeira sessão de React Native do
desenvolvedor — o card é deliberadamente contido: uma tela, um fluxo.

## Problema

Não existe app. O maior desconhecido do projeto (captura de áudio em RN +
permissões) precisa ser atacado agora, como decidido no roadmap.

## Proposta técnica

- `apps/mobile` com `create-expo-app` (TS), estrutura mínima de navegação
  (expo-router) com uma tela de conversa.
- Gravação com `expo-audio`: pedir permissão de microfone (fluxo de negado
  incluído), gravar com **limite de duração** (config — lição §7.4),
  visualizar estado (idle/gravando/pronto), regravar/descartar.
- Reprodução local do que foi gravado (validação antes de existir backend na
  jornada).
- Rodar no aparelho físico via Expo Go.

## Escopo

- **In:** o acima. **Out:** upload/polling/playback da resposta (CARD-012);
  qualquer estilização além do funcional.
- **Herdado do CARD-004:** este é o card em que nasce a skill
  `voicecoach-cliente` (`.claude/skills/`), irmã da `voicecoach-arquitetura`.
  Ela foi adiada de propósito — regra escrita antes de existir tela é letra
  morta. Fontes a destilar: ADR-0002 (Expo + web separada), ADR-0007 (token em
  `expo-secure-store`, nunca AsyncStorage), ADR-0008 (tipos gerados do OpenAPI,
  `min_supported_app_version`), ADR-0003 (upload + polling com backoff).

## Critérios de aceite

- **Dado** primeira abertura, **quando** toco em gravar, **então** o app pede
  permissão; negada ⇒ mensagem com caminho para configurações.
- **Dado** gravação ativa, **quando** atinge o limite de duração, **então**
  para sozinha e informa.
- **Dado** um áudio gravado, **então** consigo ouvi-lo e regravar.
- Funciona no aparelho físico (iOS ou Android — o que estiver à mão).

## Riscos

Primeiro contato com RN: estimativa pode estourar — se estourar, o corte é
na UX (estados mínimos), nunca no fluxo de permissão.

## Objetivo de aprendizado

O modelo mental do RN vs React web: componentes nativos (View/Text/Pressable
vs div/button), o ciclo de permissões de plataforma, e hooks sobre recursos
nativos (expo-audio) — onde o "é só React" termina.

## Ajuste da reconstrução (2026-08-19)

**O card sobrevive praticamente intacto** — gravação, permissões e limite de
duração não mudam com a cascata. Dois acréscimos:

- **Por que agora:** é o único card do caminho crítico que não depende de nada
  do backend e pode correr em paralelo com 006–010. Deixá-lo para o fim
  atrasaria a medição ponta a ponta, que é o que valida o alvo de 1,8 s.
- **Um requisito novo, vindo do [ADR-0026](../adr/0026-entrega-progressiva-por-sse-com-polling-como-contrato-de-recuo.md):**
  ao montar o app, verificar **dentro do Expo Go** se o consumo de SSE é viável
  (`react-native-sse` ou `fetch` com streaming). Descobrir isso no CARD-012, com
  a fatia inteira pronta, é caro; aqui custa meia hora. Se exigir dev build, o
  CARD-012 já entra sabendo qual recuo vai usar.
- A skill `voicecoach-cliente` continua nascendo aqui, e agora destila também o
  ADR-0026 (transporte) e o ADR-0024 (URL de trecho expirada).

---

## Execução (2026-08-24)

Branch `card-011-app-expo-gravacao`. **Status: em execução** — o que falta está
em "Pendências", e nenhum item foi marcado como cumprido sem evidência.

### Decisões tomadas nesta sessão (as quatro foram ao desenvolvedor antes da primeira linha de código)

| Decisão | Escolha | Onde ficou registrada |
|---|---|---|
| Lint/format do TypeScript | **Biome** (uma ferramenta, uma config — o argumento que fez o `ruff` ganhar) | [ADR-0043](../adr/0043-quality-gates-do-cliente-typescript-com-biome.md) |
| `expo-router` com uma tela | **Entra agora** — contra a recomendação do agente, e o deep linking provou-se útil na mesma sessão | [ADR-0044](../adr/0044-dependencias-de-arranque-do-app-expo-e-convivencia-com-pnpm.md) §3 |
| Teste automatizado de RN | **Adiado com gatilho escrito** | ADR-0043 item 6 |
| Fidelidade visual | **Tokens agora**; fonte e dark mode se sobrasse | ver Pendências |
| Convivência Expo↔pnpm | **Decidida por evidência**, não por opinião: nada de `.npmrc` | ADR-0044 §2 |

### Item de ADR da DoD — critério citado (LEARNING-0003)

Conferido contra a lista "Quando um ADR é OBRIGATÓRIO" de `docs/adr/README.md`:

- **ADR-0043** — critério **1** (dependências: `@biomejs/biome`, `typescript`) e
  critério **6** (contraria convenção estabelecida: o ADR-0015 descreve três
  anéis que, até aqui, só cobriam `backend/`).
- **ADR-0044** — critério **1** (`expo-router`, `expo-audio`, `expo-linking`,
  `expo-constants` e os peers do roteador). O critério **2** foi **avaliado e
  não se aplicou**: nenhum `.npmrc` foi necessário, então a resolução de
  módulos do repositório não mudou — e registrar o "não se aplicou" é o que
  impede a próxima sessão de refazer a investigação.
- **O spike de SSE não gerou ADR**: ele alimenta o ADR-0026, que já decidiu o
  transporte. O resultado medido está no ADR-0044 e na skill.

### Evidência dos critérios de aceite

| Critério | Estado | Evidência |
|---|---|---|
| App sobe no Simulador | ✅ | `iOS Bundled 3488ms node_modules/.pnpm/expo-router@57.0.15_…/entry.js (1280 modules)` — captura enviada |
| App sobe no aparelho físico | ⏳ | **não verificado** — depende do desenvolvedor |
| Permissão: pede ao tocar em gravar | ✅ | o desenvolvedor tocou, concedeu e gravou no Simulador |
| Negada ⇒ caminho para configurações | ⏳ | implementado (artboard 13 + `Linking.openSettings()`); **exige aparelho físico** — o Simulador não reproduz "negada permanentemente" |
| Para sozinha no limite e informa | ✅ | **par completo**: limite baixado para 5 s em `app.json > extra`, app recarregado, gravação iniciada e deixada correr. Parou **sozinha em 0:05** e informou — *"Chegamos ao limite de 5s — sua fala foi guardada até aqui."* — com o áudio preservado (player `0:00 / 0:05`). Limite revertido para 90 s |
| Ouvir o gravado e regravar | ✅ | player local com `0:01 / 0:01` e o link `regravar`, sem sair da tela |
| Estado "gravando" (sem artboard) derivado do style guide | ✅ | capturado: `Gravando…`, contador `0:02 / 0:05`, botão em **quadrado**, halo de **pulso**, "Toque para parar" |
| Compila contra os tipos gerados | ✅ | ver "O gate morde" abaixo |
| Tokens do design num lugar só | ✅ | `src/theme/tokens.ts`, com os hex do artboard 17 |
| Spike de SSE respondido | ✅ | ver abaixo |
| Gate de TypeScript que roda e morde | ✅ | ver abaixo |
| Skill `voicecoach-cliente` | ✅ | `.claude/skills/voicecoach-cliente/` |
| Divergências do design registradas | ✅ | skill §Design + `TelaConversa.tsx` |

### O spike de SSE, respondido com evidência

Dentro do **Expo Go (SDK 57.0.0)**, no Simulador iOS 26.5, contra o endpoint
real `GET /v1/turns/{id}/events` do CARD-010, com backend + worker + compose de
pé e um turn **processando ao vivo**:

| | `fetch` global (RN 0.86) | `expo/fetch` |
|---|---|---|
| turn ao vivo | `transcribed` +686 ms · `chunk 0` **+1653 ms** · `chunk 1` +2782 ms · `feedback` +2788 ms · `completed` +2867 ms — **5 leituras do stream** | testado no turn já pronto |
| turn já completo | 1 leitura (replay inteiro) | 2 leituras, +13 ms |

**Conclusão: nenhuma dependência de transporte entra.** O `EventSource` nativo
era o problema do ADR-0026 (não aceita `Authorization`); `fetch` aceita header
**e** entrega progressivamente. `react-native-sse` não é necessário, e não é
preciso dev build. O `chunk 0` em 1,65 s bate com o 1,6 s medido no backend.

**Armadilha encontrada, e ela custou uma execução:** o `sse-starlette` termina
linha com **CRLF**, então o separador de eventos é `\r\n\r\n`. O parser
procurava `\n\n`: o stream chegava (1 leitura, 200 OK) e **nenhum evento era
reconhecido** — falha silenciosa que se parece com "SSE não funciona no Expo
Go". Registrada na skill.

### O gate morde — par completo (padrão do CARD-006)

**Eixo 1 — quebra de contrato** (é o que torna verdadeira a promessa do ADR-0008):

```
$ sed -i '' 's/TurnResponse: {/TurnPayload: {/' packages/api-client/src/schema.d.ts
$ pnpm run typecheck
src/api/contrato.ts(16,42): error TS2339: Property 'TurnResponse' does not exist on type '{ … }'.
Failed
$ # revertido
$ pnpm run typecheck
Done
```

**Eixo 2 — erro de tipo comum no app:**

```
$ # const cores: number = useCores();
src/features/gravacao/TelaConversa.tsx(34,9): error TS2322: Type 'Cores' is not assignable to type 'number'.
src/features/gravacao/TelaConversa.tsx(42,66): error TS2339: Property 'fundo' does not exist on type 'number'.
Failed
```

**Bônus não planejado:** o `strict` pegou um erro real **antes de existir tela**
— `as const` nos tokens congelou cada hex num tipo literal, e a paleta dark não
era atribuível à light. E o Biome apontou uma dependência de hook faltando
(`useExhaustiveDependencies`) que teria virado `useCallback` obsoleto
intermitente.

**Os três anéis, verdes** (`uv run pre-commit run --all-files`):

```
ruff format (backend)…Passed   ruff check --fix (backend)…Passed
mypy --strict (backend)…Passed contratos de arquitetura (ADR-0012)…Passed
biome check --write (cliente)…Passed   tsc --noEmit (cliente)…Passed
```

### Achado de repositório: dois commits ficaram fora do merge do PR #15

`a002023` (os 17 artboards em PNG) e `d070490` (o prompt desta sessão) estavam
na branch do CARD-010 e **não entraram no merge**. Sem eles, `docs/design/artboards/`
não existe em `main` e o design é ilegível para qualquer sessão. Trazidos por
cherry-pick para esta branch.

**Erro do agente na mesma operação, registrado por honestidade:** os dois
cherry-picks caíram em `main` (o HEAD estava lá, apesar de o `git switch -c`
anterior ter reportado sucesso). Corrigido com `git switch -C` + `git branch -f
main origin/main`; `main` local voltou a bater com `origin/main` e nada foi
pushado.

### Regra do explicador — desfecho de cada item

| Item | Desfecho |
|---|---|
| **Pendência de topo:** decidir se a *regra* muda (postmortem proposto no CARD-009, repetido no 010) | **em aberto** — reapresentada na abertura com os três caminhos possíveis; sem resposta |
| **Q7** (`Protocol` / o que quebra quando o contrato muda) | **em aberto** — reapresentada na abertura pelo paralelo com o `tsc`; sem resposta e sem dispensa. Demonstrou-se sozinha de novo: `TurnResponse` renomeado ⇒ `error TS2339` |
| **Q1** (`src/` layout / fronteira de empacotamento) | **em aberto** — reapresentada pelo paralelo com o Metro e os symlinks do pnpm; sem resposta e sem dispensa. Demonstrou-se: o bundle resolveu via `node_modules/.pnpm/…` |
| **Pergunta nova (Q14)**, feita **no ponto da decisão**, antes de escrever o spike: *"lendo `response.body` com o `fetch` global do RN — chega em pedaços, chega tudo no fim, ou dá erro?"* | **em aberto** — feita antes do código, sobre consequência observável, conferida rodando na hora. A resposta é **(a) chega em pedaços** (5 leituras, timestamps crescentes). Sem resposta do desenvolvedor |

**Sétima sessão seguida com o item vermelho.** O item **não** está sendo marcado
como cumprido (LEARNING-0004): explicação do agente e demonstração executada não
fecham item de aprendizado.

### Correção de UX feita durante a verificação

No estado `gravado`, o rótulo abaixo do botão dizia *"Ouça o que você falou"* —
mas o botão ali **grava de novo**, não toca. O rótulo descrevia o player que está
no meio da tela. Trocado por **"Toque para gravar de novo"**: o rótulo descreve o
botão que está embaixo dele.

### Uma observação de layout que NÃO é bug

O player aparece centralizado no vazio da tela, e no artboard 01 ele está
ancorado ao fim da resposta do professor. **A diferença é ausência de conteúdo,
não erro de layout:** não existe lista de turns (bolha do aluno, resposta,
card de correção) porque ela é do CARD-012/CARD-016. Montá-la agora seria pior
que adiar — a ordem desenhada está **invertida** em relação à cascata
(ADR-0022/0023), e a lista nasceria errada.

### Pendências

| O que falta | Quem resolve |
|---|---|
| **Permissão negada permanentemente + microfone real, em aparelho físico** | o único critério que falta. O Simulador não reproduz o estado, e sem ele o item da DoD não pode ser marcado |
| Fonte `Instrument Sans` (`expo-font` + `@expo-google-fonts/instrument-sans`) | card próprio de UI |
| Dark mode verificado na prática (os tokens existem; `userInterfaceStyle: automatic`) | idem |
| Gate de teste automatizado no cliente | ADR-0043 item 6, com gatilho |
| Verificação automática da fronteira `apps/` ↔ `packages/` | skill `voicecoach-cliente`, com gatilho |
| `apps/mobile/spike-sse.tsx` sair do repositório | CARD-012 |
