# CARD-001 — Monorepo e esqueleto do backend em camadas

- **ID:** CARD-001 · **Épico:** Fase 0 — Fundação
- **Plataforma:** infra · **Esforço:** M · **Status:** concluído (2026-08-17)
- **Dependências:** nenhuma

## Contexto

Início da reescrita sobre nova fundação (veredito do diagnóstico). ADR-0002
define monorepo (apps JS + backend Python no mesmo repo); a visão §D define
as camadas.

## Problema

Não existe estrutura: o repositório só tem o protótipo congelado
(`english_teacher_bot/`) e os docs do harness.

## Proposta técnica

- Layout: `backend/` (Python, uv + pyproject, src layout:
  `src/voicecoach/{domain,application,adapters,api,worker}` com `__init__.py`
  e docstring declarando a regra da camada), `apps/mobile`, `apps/web`,
  `packages/api-client` (vazios com README), `pnpm-workspace.yaml`.
- `backend/README.md` com o mapa de dependências entre camadas (tudo aponta
  para dentro) — fonte para a skill de arquitetura (CARD-004).
- uv como gerenciador (lockfile, venv) — equivalente mental: SDK-style
  csproj + NuGet lock.

## Escopo

- **In:** estrutura de pastas, pyproject com deps mínimas (fastapi, pydantic,
  pydantic-settings), workspaces pnpm, READMEs de fronteira.
- **Out:** qualquer endpoint ou lógica (CARD-002+); configuração de CI
  (CARD-003).

## Critérios de aceite

- **Dado** o repo clonado, **quando** `uv sync` roda em `backend/`, **então**
  o ambiente instala e `uv run python -c "import voicecoach"` funciona.
- **Dado** o layout, **quando** se lê o README de qualquer camada, **então**
  a regra de dependência daquela camada está declarada.
- **Dado** a raiz, **quando** `pnpm install` roda, **então** os workspaces
  resolvem sem erro.

## Riscos

Layout de monorepo Python+JS tem armadilhas de tooling (venv vs node_modules
no mesmo repo) — mitigar mantendo cada toolchain no seu diretório.

## Objetivo de aprendizado

Entender o empacotamento Python moderno: por que src layout evita imports
acidentais do diretório de trabalho, o papel do pyproject.toml (≈ csproj) e o
que o uv resolve que pip+venv manuais não resolvem (lockfile determinístico,
≈ NuGet lock + SDK pinning).

---

## Execução (2026-08-17)

### O que foi entregue

- `backend/` com src layout, `pyproject.toml` (fastapi, pydantic,
  pydantic-settings; dev: import-linter), `.python-version` (3.12), `uv.lock`.
- Cinco camadas em `src/voicecoach/{domain,application,adapters,api,worker}`,
  cada `__init__.py` com docstring declarando sua regra de dependência e o
  equivalente mental .NET.
- `backend/README.md` com o mapa de dependências (diagrama + tabela camada →
  pode importar → proibido → equivalente .NET) — insumo do CARD-004.
- `pnpm-workspace.yaml` (`apps/*`, `packages/*`), `package.json` raiz com
  `packageManager` pinado, `.nvmrc`.
- `apps/mobile`, `apps/web`, `packages/api-client` com README declarando a
  fronteira de cada um.
- Higiene de fundação: `.editorconfig` (única convenção que atravessa as duas
  toolchains) e `.gitignore` estendido para Node/logs.

### Adição ao escopo original (aprovada em sessão)

Antes da implementação, o monorepo da empresa do desenvolvedor
(`MEDGRUPO/Front-end/MEDSoft` — Turborepo + pnpm, `apps/*` + `packages/*`) foi
analisado como referência. O achado aproveitado: eles mantêm as regras de
arquitetura como artefato **executável** (`docs/ai/rules/architecture.json`
alimentando um validador de PR) em vez de só prosa.

Daí a única adição ao escopo do card: **`import-linter`** com contratos em
`[tool.importlinter]` no `pyproject.toml`. Motivo — em C# a fronteira de camada
é imposta pelo `.csproj` (Domain não referencia Infrastructure e o compilador
recusa); em Python qualquer módulo importa qualquer módulo, então a fronteira
só existe se for lint. Custo zero, offline (respeita o ADR-0010, ao contrário
do validador por IA do MEDSoft, que gasta por PR).

O que foi deliberadamente **não** copiado do MEDSoft está registrado em
`backend/README.md` e na análise da sessão: `shamefully-hoist=true` no `.npmrc`
(mascara phantom dependencies), `COPY . .` antes do install no Dockerfile
(invalida cache de layer — relevante para o CARD-002), logs e PNGs versionados
na raiz, e o gate de PR por LLM.

### Evidência dos critérios de aceite

| Critério | Comando | Resultado |
|---|---|---|
| `uv sync` instala | `cd backend && uv sync` | 20 pacotes instalados, `voicecoach` buildado do fonte |
| `import voicecoach` funciona | `uv run python -c "import voicecoach"` | OK, resolvendo de `src/voicecoach/__init__.py` |
| Regra de dependência declarada por camada | docstring de cada `__init__.py` + tabela no `backend/README.md` | 5 camadas cobertas |
| Workspaces resolvem | `pnpm install` na raiz | `Done in 264ms`, exit 0 |

Verificação extra (a regra vale mais que a prosa): `uv run lint-imports` →
`3 kept, 0 broken`. Com `import fastapi` injetado em `domain/` de propósito,
o contrato quebrou apontando arquivo e linha (`voicecoach.domain -> fastapi
(l.16)`) — depois revertido. O gate não está apenas verde por estar vazio.

### Regra do explicador — status honesto

As 2 perguntas foram feitas (src layout; `api | worker` na mesma camada), mas
o desenvolvedor pediu que o agente seguisse com a explicação em vez de
responder. Portanto o item da DoD foi cumprido pelo **caminho alternativo** do
CLAUDE.md ("me explique até eu conseguir defender em entrevista"), não pela
verificação por resposta. As duas explicações, resumidas:

1. **`src/` layout** — sem ele, o diretório de trabalho entra no `sys.path` e
   `import voicecoach` resolve para a árvore de fontes mesmo que o pacote não
   esteja corretamente empacotado. Mascara erro de empacotamento (subpacote
   fora do wheel, recurso não-`.py` ausente, dependência usada e não
   declarada), que só aparece quando o código roda a partir do artefato — o
   container do CARD-002 ou o CI do CARD-003. Com `src/`, o import só funciona
   porque `uv sync` instalou o pacote: local exercita o mesmo caminho do
   container. ≈ testar contra o `.nupkg` em vez da pasta do projeto.
2. **`"api | worker"` na mesma camada** — empilhados, `api -> worker` seria
   permitido. São dois entrypoints do mesmo núcleo (processos separados,
   ADR-0005), não camadas um do outro; o que compartilham deve ser o caso de
   uso em `application`. A seta proibida barra o atalho síncrono (chamar o
   pipeline direto em vez de enfileirar, ressuscitando o request bloqueante de
   12–15s) e o acoplamento de deploy. Verificado empiricamente: a violação
   injetada produziu `voicecoach.api is not allowed to import
   voicecoach.worker`.

### Dívidas registradas

- **Sem testes** — não há infraestrutura de testes ainda (CARD-003). Nada aqui
  é lógica executável; a verificação foi por comando, conforme evidência acima.
- **`tests/` e `alembic/` não criados** — entram nos cards que os justificam
  (CARD-003 e CARD-005). Pasta vazia sem dono não entra no esqueleto.
- **Contratos `forbidden` cobrem só dependências já instaladas** (`fastapi`,
  `pydantic`). Ao adicionar SQLAlchemy, `anthropic` ou `redis`, incluir na
  lista do contrato no mesmo commit — anotado no `backend/README.md`.
- **`domain` proibido de importar pydantic** (leitura estrita da visão §D:
  domínio usa só a stdlib). Decisão barata de reverter — uma linha no contrato
  — se um ADR futuro decidir que pydantic é aceitável no domínio.
- **Sem Turborepo** — só ganha sentido com ≥2 pacotes buildáveis; reavaliar no
  CARD-003.
