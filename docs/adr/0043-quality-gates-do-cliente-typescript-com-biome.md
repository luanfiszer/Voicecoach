# ADR-0043 — Os quality gates do cliente: `tsc --strict` e Biome, nos mesmos três anéis

- **Status:** aceito
- **Data:** 2026-08-24
- **Complementa:** [ADR-0015](0015-quality-gates-tres-aneis.md) (três anéis, hoje só
  no backend), [ADR-0008](0008-contrato-api-versionamento-e-tipos-gerados.md)
  (tipos gerados), [ADR-0010](0010-politica-de-custo-projeto-pessoal.md)
- **Critérios de obrigatoriedade** (`docs/adr/README.md`): **1 — introduz
  dependência externa** (`@biomejs/biome`, `typescript`) e **6 — contraria uma
  convenção estabelecida**: o ADR-0015 descreve três anéis de qualidade que, até
  aqui, cobriam **apenas `backend/`**.

## Contexto

O CARD-011 criou o primeiro código TypeScript do produto. Antes dele, o
repositório tinha uma assimetria que ninguém havia declarado:

| Anel (ADR-0015) | Backend | Cliente, antes deste ADR |
|---|---|---|
| 1 — agente (`PostToolUse`) | `ruff` + `mypy` | **nada** |
| 2 — pre-commit | 11 hooks, **todos** com `files: ^backend/` | **nada** |
| 3 — CI | job `backend` (ruff, mypy, pytest, import-linter) | **nada** |

E os cinco comandos da Definition of Done do `CLAUDE.md` são, sem exceção, de
`backend/`.

A consequência não era estética. O **ADR-0008 item 4 promete** que "quebra de
compilação dos clientes acusa breaking change antes do runtime". O job `openapi`
do CI prova que os tipos gerados estão **em dia com o backend** — mas ninguém
compilava cliente nenhum contra eles. A promessa era, literalmente, falsa: um
campo renomeado em `/v1` passaria pelo CI inteiro, verde, e só apareceria no
aparelho de alguém.

Um TypeScript frouxo ao lado de um `mypy --strict` também é incoerência que
alguém herda: o mesmo repositório diria "tipagem é lei" de um lado e "tipagem é
sugestão" do outro.

## Decisão

**Os três anéis do ADR-0015 passam a cobrir `apps/` e `packages/`, com duas
ferramentas: `tsc --noEmit` em `strict` e `biome`.**

1. **Type checking: `tsc --noEmit`** com `strict: true` e mais três flags que o
   `strict` não liga sozinho — `noUncheckedIndexedAccess`, `noImplicitOverride`,
   `noFallthroughCasesInSwitch`. É o par do `mypy --strict`.
2. **Lint e formatação: `biome`**, uma ferramenta e uma configuração
   (`biome.json` na raiz, 88 colunas — o mesmo do `ruff`). Regras: `recommended`
   + o domínio `react` + um punhado explícito (`useExhaustiveDependencies`,
   `useHookAtTopLevel`, `noExplicitAny`, `noNonNullAssertion`).
3. **Onde roda, do mais barato ao mais lento** — os mesmos três anéis:

   | Anel | O que roda no cliente |
   |---|---|
   | 1 — agente | `biome check --write <arquivo>` + `pnpm -r run typecheck` |
   | 2 — pre-commit | `biome check --write` (`files: ^(apps\|packages)/`) + `tsc` com `pass_filenames: false` |
   | 3 — CI | job `mobile`: `pnpm install --frozen-lockfile`, `pnpm run lint`, `pnpm run typecheck` |

4. **O `tsc` roda sobre o projeto inteiro, não sobre os arquivos do commit**
   (`pass_filenames: false`) — **pelo mesmo motivo que o `mypy`** (ADR-0015):
   tipagem é propriedade do grafo. Mudar a assinatura de um hook quebra quem o
   chama, e quem o chama pode não estar no commit.
5. **Os hooks rodam como `language: system`**, via `pnpm exec`, e não no
   virtualenv isolado do `pre-commit` — mesma justificativa do backend: sem o
   `node_modules` do workspace, o Biome e o `tsc` não enxergam nem as
   dependências nem os tipos gerados.
6. **O gate de teste automatizado de RN NÃO entra agora, e o gatilho está
   escrito:** `jest-expo` + `@testing-library/react-native` + mocks de módulo
   nativo é superfície real, e o que o CARD-011 entrega é quase todo I/O de
   plataforma (microfone, permissão) — a parte que o teste unitário não alcança.
   **Gatilho:** a primeira lógica de cliente pura o bastante para ser testada
   fora de um componente (candidata natural: a máquina de estados de
   `useGravacao`, quando ela ganhar um segundo consumidor). Adiado por escrito,
   não em silêncio.

## Alternativas consideradas

### Alternativa A — ESLint + Prettier (o padrão do ecossistema RN)

- **O que é:** o par clássico; `create-expo-app` já traz `eslint-config-expo`.
- **Por que foi rejeitada:** é o mesmo argumento que fez o `ruff` ganhar do trio
  `black`+`flake8`+`isort` no ADR-0015 — duas ferramentas, duas configurações e
  duas chances de discordarem sobre a mesma linha. O que se perde é honesto e
  vale registrar: o ecossistema de plugins do ESLint é maior, e regras
  específicas de React Native (`eslint-plugin-react-native`) **não têm
  equivalente no Biome**. **Gatilho para reavaliar:** aparecer uma classe de bug
  de RN que só um plugin de ESLint pegue.

### Alternativa B — `tsc` sem `strict`, ou `strict` só em parte do código

- **O que é:** ligar a tipagem aos poucos, para não travar o começo.
- **Por que foi rejeitada:** o ADR-0015 já respondeu isto para o backend ("o
  gate precisa existir *antes* do código que ele vigia, ou nasce negociando com
  o que já está lá"). Um app de uma tela é exatamente o momento mais barato para
  ligar tudo — e a primeira coisa que o `strict` pegou nesta sessão foi um erro
  real de tipagem nos tokens de design, antes de qualquer tela existir.

### Alternativa C — Só CI, sem os anéis locais

- **Por que foi rejeitada:** mesma razão do ADR-0015 Alternativa C, agravada
  pelo custo: o job do cliente instala o workspace inteiro. Descobrir uma
  dependência de hook faltando 4 minutos depois, num log, custa muito mais que
  descobrir no instante da edição.

### Alternativa D — `oxlint` / `dprint` / outra combinação nova

- **Por que foi rejeitada:** ganho marginal sobre o Biome e uma ferramenta a
  mais no vocabulário do projeto. Visão §F: sem peça nova sem gatilho.

## Consequências

**Positivas**

- **A promessa do ADR-0008 vira verdade verificável.** Demonstrado nesta sessão
  com o par completo: renomear `TurnResponse` no schema gerado ⇒
  `error TS2339: Property 'TurnResponse' does not exist`; revertido ⇒ verde.
- A assimetria do ADR-0015 fecha: as duas toolchains do monorepo têm os mesmos
  três anéis, com a mesma filosofia (redundância proposital).
- O linter funciona como material didático contínuo para quem está aprendendo o
  idioma — na primeira sessão ele apontou uma dependência de hook faltando que
  teria virado bug intermitente de `useCallback` obsoleto.
- Custo em dinheiro: **R$ 0** (ADR-0010). Biome roda offline, em Rust, em ~350 ms
  sobre o repositório.

**Negativas — o preço aceito**

- **Duas ferramentas de qualidade a mais para versionar e atualizar**, e uma
  segunda configuração de formatação (88 colunas replicado no `biome.json` e no
  `pyproject.toml` — a mesma decisão escrita em dois lugares).
- **O anel 1 ficou mais lento no cliente que no backend**: o `tsc` roda sobre o
  workspace inteiro a cada edição de `.ts`/`.tsx` (~3–5 s), contra ~1–2 s do
  `mypy`. Aceito pelo mesmo motivo: checar um arquivo isolado é um verde falso.
- **O ecossistema de lint de RN fica de fora** enquanto o Biome não tiver as
  regras equivalentes (Alternativa A).
- **O CI ficou com três jobs** (`backend`, `mobile`, `openapi`), e o `mobile` e o
  `openapi` instalam o mesmo workspace pnpm — duplicação de ~30 s por PR.
  Aceito: unificá-los acoplaria a verificação do contrato à do app.
- **Nenhum gate de teste no cliente** até o gatilho do item 6 disparar. Esta é a
  dívida mais visível deste ADR, e ela está declarada.

**Equivalente mental .NET:** o que você já faz com `<Nullable>enable</Nullable>`
+ `TreatWarningsAsErrors` + `.editorconfig` com analyzers, só que aqui o
compilador **não** é um gate obrigatório — `tsc --noEmit` é um passo que alguém
precisa escolher rodar, e o Metro empacota código que não compila sem reclamar.
É por isso que os três anéis não são exagero: eles substituem a barreira de
compilação que o TypeScript, ao contrário do C#, não impõe sozinho.
