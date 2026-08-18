# backend — API Python do Voicecoach

Backend em camadas consumido pelos dois clientes (`apps/mobile`, `apps/web`).
Este README é a **fonte da regra de arquitetura** deste diretório — é o insumo
da skill de arquitetura (CARD-004).

Estado: **esqueleto** (CARD-001). Nenhuma lógica de aplicação ainda; as
camadas existem vazias com sua regra declarada.

---

## Mapa de dependências

```
        ┌──────────────┐        ┌──────────────┐
        │     api      │        │    worker    │   entrypoints (irmãos,
        │  (FastAPI)   │        │    (arq)     │   não se importam)
        └──────┬───────┘        └──────┬───────┘
               │                       │
               └───────────┬───────────┘
                           ▼
                    ┌──────────────┐
                    │   adapters   │   implementam as portas
                    └──────┬───────┘
                           ▼
                    ┌──────────────┐
                    │ application  │   casos de uso + portas (Protocol)
                    └──────┬───────┘
                           ▼
                    ┌──────────────┐
                    │    domain    │   regras puras — não conhece ninguém
                    └──────────────┘
```

**A regra, em uma linha: tudo aponta para dentro.** Uma seta que suba é um bug
de arquitetura, não uma questão de gosto.

| Camada | Pode importar | Proibido | Equivalente .NET |
|---|---|---|---|
| `domain` | só a stdlib | framework, SDK, IO — **qualquer** dependência externa | `Domain` |
| `application` | `domain` | FastAPI, SQLAlchemy, SDKs de IA, Redis, S3 | `Application` |
| `adapters` | `application`, `domain`, libs externas | `api`, `worker`; regra de negócio | `Infrastructure` |
| `api` | `application`, `adapters`, `domain` | ser importada por outra camada; regra de negócio | `API` (controllers + `Program.cs`) |
| `worker` | `application`, `adapters`, `domain` | ser importada por outra camada; regra de negócio; importar `api` | host de `BackgroundService` |

O docstring de cada `__init__.py` repete a regra da sua camada — quem abre o
arquivo lê a regra antes de escrever a primeira linha.

### A regra é executável

Prosa não impede import. Os contratos vivem em `[tool.importlinter]` no
`pyproject.toml`:

```bash
uv run lint-imports
```

> **Por que isso é necessário aqui e não em C#:** no .NET a barreira é o
> arquivo de projeto — `Domain.csproj` não referencia `Infrastructure.csproj`
> e o compilador impede o acoplamento. Em Python qualquer módulo importa
> qualquer módulo; não existe fronteira de compilação. Logo, a fronteira tem
> que ser um lint. Equivalente mental: `NetArchTest`/`ArchUnitNET`.

Os contratos `forbidden` listam apenas dependências **já instaladas** (hoje
`fastapi` e `pydantic`). Ao adicionar uma dependência nova que não pode
vazar para dentro (SQLAlchemy, `anthropic`, `redis`), acrescente-a à lista
do contrato no mesmo commit.

---

## Estrutura

```
backend/
├── pyproject.toml        # manifesto + contratos de arquitetura
├── uv.lock               # resolução determinística (commitado)
├── .python-version       # 3.12
└── src/
    └── voicecoach/
        ├── domain/
        ├── application/  # ports/ com os Protocol
        ├── adapters/
        ├── api/
        └── worker/
```

`tests/` e `alembic/` entram nos cards que os justificam (testes e
persistência) — o esqueleto não antecipa pasta vazia sem dono.

---

## Ambiente

Pré-requisito: [uv](https://docs.astral.sh/uv/).

```bash
cd backend
uv sync                                   # cria .venv e instala do lockfile
uv run python -c "import voicecoach"      # sanidade
uv run lint-imports                       # contratos de arquitetura
```

### O que cada peça faz (para quem vem de .NET)

| Peça | O que é | Equivalente mental |
|---|---|---|
| `pyproject.toml` | manifesto do projeto: nome, versão, dependências, config das ferramentas | `.csproj` (SDK-style) + `.editorconfig` de ferramentas num arquivo só |
| `uv` | resolve, instala, cria a venv e roda comandos no ambiente | `dotnet restore` + `dotnet run` + gerência do SDK |
| `uv.lock` | versões exatas de **toda** a árvore, commitado | `packages.lock.json` do NuGet |
| `.python-version` | fixa a versão do interpretador | `global.json` (SDK pinning) |
| `uv run <cmd>` | roda no ambiente do projeto sem "ativar" nada | `dotnet <tool>` |
| `.venv/` | o ambiente isolado; não se commita | `obj/`+`bin/` com os pacotes restaurados |

**Por que `src/` layout.** Sem ele, o diretório de trabalho entra no caminho de
import e `import voicecoach` acha a pasta do código-fonte mesmo que o pacote
nunca tenha sido instalado. Isso mascara erro de empacotamento: funciona na sua
máquina, quebra no container. Com `src/`, o import só resolve porque o pacote
foi de fato instalado no ambiente — o teste roda contra o artefato, não contra
a árvore de arquivos. É o mais perto que Python chega de "referenciar o
assembly em vez do diretório".

**Por que `uv` e não `pip` + `venv`.** `pip install -r requirements.txt` não
trava a árvore transitiva: duas instalações no mesmo `requirements.txt` podem
render versões diferentes de dependências indiretas — a `.venv` do protótipo em
`english_teacher_bot/` tem exatamente esse problema. `uv` produz `uv.lock` com
a árvore inteira resolvida, gerencia o interpretador e é ordens de grandeza
mais rápido. É a diferença entre restaurar com e sem lockfile.
