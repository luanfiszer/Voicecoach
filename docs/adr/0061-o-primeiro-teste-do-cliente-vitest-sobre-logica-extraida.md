# ADR-0061 — O primeiro teste do cliente: `vitest` sobre lógica extraída, não `jest-expo` sobre componente

- **Status:** aceito
- **Data:** 2026-09-10
- **Complementa:** [ADR-0043](0043-quality-gates-do-cliente-typescript-com-biome.md)
  (item 6 — o gate de teste adiado **com gatilho escrito**),
  [ADR-0015](0015-quality-gates-tres-aneis.md) (os três anéis),
  [ADR-0010](0010-politica-de-custo-projeto-pessoal.md)
- **Critérios de obrigatoriedade** (`docs/adr/README.md`): **1 — introduz
  dependência externa** (`vitest`, e com ele `esbuild`) e **6 — contraria uma
  convenção estabelecida**: o ADR-0043 item 6 decidiu, por escrito, que o
  cliente **não** teria gate de teste automatizado.

## Contexto

O CARD-042 investiga um bug de playback: ao tocar em gravar, o professor
continua falando. A correção é de uma linha — `pause()` antes de `remove()` —,
e é exatamente aí que está o problema.

**A ordem `pause()` → `remove()` é uma invariante invisível.** Inverter as duas
linhas não quebra compilação, não acusa no `tsc --strict`, não acusa no Biome,
não muda nenhuma tela. O único lugar onde a violação aparece é no ouvido de quem
usa o app, num aparelho físico, num instante que dura menos de um segundo. É a
classe de regra que nenhum dos gates existentes alcança e que só um teste segura.

O ADR-0043 item 6 previu este momento e escreveu o gatilho:

> **Gatilho:** a primeira lógica de cliente pura o bastante para ser testada
> fora de um componente (candidata natural: a máquina de estados de
> `useGravacao`, quando ela ganhar um segundo consumidor).

O gatilho disparou por um caminho diferente do previsto — não foi um segundo
consumidor de `useGravacao`, foi a necessidade de fixar uma **ordem de chamadas
ao mundo nativo**. Mas a condição substantiva é a mesma: existe, pela primeira
vez, lógica de cliente que não depende de plataforma nenhuma.

O que o ADR-0043 recusava continua de pé, e é bom lembrar por quê: montar
`jest-expo` + `@testing-library/react-native` + mocks de módulo nativo para
testar **I/O de plataforma** (microfone, permissão, sessão de áudio) é
superfície grande para testar o que o teste unitário não alcança de verdade.
Nada aqui reabre isso.

## Decisão

**Entra `vitest`, rodando em Node puro sobre lógica extraída de componente. O
código sob teste não pode importar nada — nem `react`, nem `expo-audio`.**

1. **`vitest`** como runner, na raiz do monorepo (`devDependency` de workspace),
   com `vitest.config.ts` mínimo: `environment: 'node'`, sem setup file, sem
   `jsdom`, sem transform de React Native.
2. **A regra que mantém o custo baixo é sobre o código, não sobre o runner:**
   o que vai para teste é extraído para um módulo **sem imports**
   (`src/features/turno/silencio.ts` é o primeiro). Se um teste precisar de mock
   de módulo nativo, a resposta certa é quase sempre *extrair mais*, não
   *mockar mais*.
3. **O dublê é objeto literal, não framework de mock.** Tipagem estrutural do
   TypeScript: ter `pause` e `remove` já satisfaz `PlayerSilenciavel`. É a
   mesma propriedade que o `Protocol` dá no backend (Q7 da fila de perguntas) —
   e o momento em que um dublê desatualizado é reprovado é o **`tsc`**, com o
   teste ainda verde.
4. **Onde roda** — os três anéis do ADR-0015, como o ADR-0043 já fazia:

   | Anel | O que passa a rodar |
   |---|---|
   | 1 — agente | inalterado (`biome check --write` + `typecheck`) |
   | 2 — pre-commit | `vitest run`, `pass_filenames: false` |
   | 3 — CI | `pnpm run test` no job `mobile` |

   `pnpm run gates` na raiz passa a ser `lint && typecheck && test`.
5. **Não há limiar de cobertura no cliente**, e isso é deliberado — diferente do
   backend, que tem 80% global e 90% no núcleo (ADR-0015/0019). A maior parte do
   cliente é I/O de plataforma que este runner não alcança; um número de
   cobertura aqui mediria o que foi **extraído**, não o que foi **verificado**,
   e pressionaria na direção errada — extrair por métrica em vez de por clareza.
   **Gatilho para reabrir:** quando existirem três ou mais módulos extraídos com
   regra de negócio de verdade.
6. **O que o teste do cliente NÃO substitui, escrito para não se esquecer:** o
   Simulador não prova microfone, latência nem "permissão negada
   permanentemente" (ADR-0054 item 3), e o Node prova menos ainda. Teste verde
   aqui significa "a ordem das chamadas está certa" — **nunca** "o som parou".
   O número no ouvido continua vindo do aparelho.
7. **`esbuild` precisa de liberação explícita de build script**
   (`allowBuilds: esbuild: true` no `pnpm-workspace.yaml`). O pnpm bloqueia
   script de instalação por padrão; a liberação é pacote a pacote e fica
   versionada — não é `--unsafe-perm` global.

## Alternativas consideradas

### Alternativa A — `jest-expo` + `@testing-library/react-native`

- **O que é:** o padrão do ecossistema Expo/RN: preset de Jest que transforma o
  código do RN, com biblioteca para renderizar componentes e hooks de verdade.
  Permitiria testar `useFilaDePlayback` inteiro, com `renderHook`.
- **Por que foi rejeitada:** para fixar uma ordem de duas chamadas, traria o
  preset inteiro do React Native, a transformação de módulos nativos e mocks de
  `expo-audio` — e o dublê de `expo-audio` seria escrito por mim, o que faz o
  teste provar que **o meu mock** se comporta como eu imagino que o nativo se
  comporta. É precisamente a crença que este card descobriu ser falsa
  (`remove()` não cala). Um teste que confirma a suposição errada é pior que
  nenhum. É também o oposto da Parte F da visão.
- **Gatilho para reabrir:** quando houver componente com lógica de renderização
  condicional complexa o bastante para que ler o JSX não baste.

### Alternativa B — não ter teste; verificar só no aparelho

- **O que é:** manter o ADR-0043 item 6 como está e provar a ordem no iPhone, com
  gravação de tela, a cada vez que alguém mexer na fila.
- **Por que foi rejeitada:** a invariante é invisível e o custo de verificá-la é
  alto (cabo, build, certificado de 7 dias, ouvido). Regra cuja verificação custa
  caro é regra que volta a ser violada — e **esta já foi violada uma vez**, que é
  o motivo de o CARD-042 existir. O teste custa 100 ms.

### Alternativa C — `node:test` (o runner nativo do Node)

- **O que é:** `node --test`, embutido no runtime desde o Node 18. Zero
  dependência nova, que é o argumento mais forte contra o `vitest` sob o
  ADR-0010.
- **Por que foi rejeitada:** ele não entende TypeScript sem um passo a mais
  (`--experimental-strip-types` ou `tsx`), e o que se ganharia em "zero
  dependência" se perderia em configuração manual e em atrito diário. O `vitest`
  lê o `tsconfig` e os aliases do projeto sem nada. Custo em dinheiro: zero nos
  dois casos (ADR-0010 é sobre **dinheiro**, não sobre número de pacotes).

## Consequências

- **Positivas:** a invariante do CARD-042 fica **provada e barata de reprovar**
  (demonstrado: ordem invertida ⇒ 3 de 5 testes vermelhos em 105 ms). O cliente
  ganha o terceiro gate que o backend já tinha, e o ADR-0043 item 6 fecha pelo
  caminho que ele mesmo previu. A regra "extrair para testar" empurra o código
  na direção certa: o módulo sem imports é mais fácil de ler, não só de testar.
- **Negativas:** mais uma ferramenta e mais um vocabulário no repositório
  (`vitest` do lado TS, `pytest` do lado Python — funções parecidas, APIs
  diferentes). Um binário nativo (`esbuild`) passa a ser compilado na
  instalação, e o pnpm exige liberá-lo por escrito. E há um risco real de
  **falsa segurança**: o teste prova ordem de chamadas, não comportamento
  nativo; o item 6 existe para que ninguém leia "5 passed" como "o som para".
- **Equivalente mental (.NET):** `vitest` ≈ `xUnit` + `dotnet test`; o
  `PlayerSilenciavel` com objeto literal é o que você faria com uma interface
  pequena e uma classe de teste escrita à mão, em vez de `Moq`. A diferença sem
  paralelo em C# é que aqui **nada declara que implementa a interface** — a
  compatibilidade é estrutural, verificada pela forma do objeto, e é por isso que
  o dublê cabe em quatro linhas.
