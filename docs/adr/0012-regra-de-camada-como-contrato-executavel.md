# ADR-0012 — Regra de camada como contrato executável (import-linter)

- **Status:** aceito
- **Data:** 2026-08-17
- **Complementa:** visão §D (camadas do backend), ADR-0010 (política de custo)

## Contexto

A visão §D declara o mapa de dependências do backend: `api | worker` →
`adapters` → `application` → `domain`, com `domain` puro. Até o CARD-001 essa
regra existia apenas em prosa (documento de visão, README, docstrings).

Três forças tornaram isso insuficiente:

1. **Python não tem barreira de compilação.** No .NET, `Domain.csproj` não
   referencia `Infrastructure.csproj` e o compilador recusa o acoplamento — a
   arquitetura é imposta pela ferramenta. Em Python, qualquer módulo importa
   qualquer módulo; a fronteira existe apenas na disciplina de quem escreve.
2. **O projeto é executado sessão a sessão, com agente.** Cada sessão começa
   sem memória do que a anterior combinou. Regra que depende de lembrar é
   regra que erode.
3. **Referência de campo.** O monorepo MEDSoft (empresa do desenvolvedor,
   Turborepo + pnpm) mantém suas regras arquiteturais como artefato
   executável — `docs/ai/rules/architecture.json` com padrões bloqueantes
   ("features não podem importar de `apps/*`") alimentando um validador de PR
   no CI. Confirmou que a regra em prosa não sobrevive a um time; a regra
   mecânica sim.

## Decisão

**A regra de camada vive no `pyproject.toml` como contrato do `import-linter`,
verificável por `uv run lint-imports`.** A prosa (README, docstrings) continua
existindo para ensinar o porquê; o contrato é quem impede.

Contratos definidos no CARD-001:

1. **Camadas** — `layers = ["api | worker", "adapters", "application", "domain"]`
   com `containers = ["voicecoach"]`. `api` e `worker` ficam na **mesma**
   camada, separados por `|`, o que os torna independentes: nenhum pode
   importar o outro. São dois entrypoints do mesmo núcleo (processos separados,
   ADR-0005), não camadas um do outro.
2. **`domain` puro** — contrato `forbidden` proibindo import de framework.
   Sub-decisão explícita: **`domain` usa apenas a biblioteca padrão, incluindo
   `dataclasses` em vez de pydantic.**
3. **`application` sem framework** — contrato `forbidden` para FastAPI.

Regras de manutenção:

- Contratos `forbidden` só podem citar dependências **instaladas**. Ao
  adicionar uma dependência que não pode vazar para dentro (SQLAlchemy,
  `anthropic`, `redis`, `httpx`), incluí-la na lista **no mesmo commit** que a
  adiciona.
- O gate no CI entra no CARD-003, junto com ruff e mypy.

## Alternativas consideradas

### Alternativa A — Manter só a prosa (README + docstrings por camada)
- O que é: declarar a regra no `backend/README.md` e no docstring de cada
  `__init__.py`, confiando na revisão para pegar violações.
- Por que foi rejeitada: prosa não impede import. O diagnóstico do protótipo
  já mostrou o padrão — o código deriva do que se pretendia, e ninguém percebe
  no momento em que acontece. O custo da alternativa mecânica é uma dependência
  de dev e cinco linhas de TOML; o custo da prosa é uma refatoração quando a
  seta errada já tiver dez chamadores.

### Alternativa B — Validador de arquitetura por LLM no PR (o padrão do MEDSoft)
- O que é: script que manda o diff para um modelo com as regras em JSON e
  bloqueia o PR conforme a resposta.
- Por que foi rejeitada: (1) **custo recorrente por PR**, o que o ADR-0010
  proíbe fora do gasto com Claude; (2) **não é determinístico** — o próprio
  prompt do MEDSoft instrui "apenas flague violations se você tiver CERTEZA
  ABSOLUTA", o que é a admissão de que o gate pode passar batido; (3) regra
  arquitetural precisa de resposta binária e reproduzível: ou a seta existe no
  grafo de imports, ou não existe. Isso é análise estática, não julgamento.

### Alternativa C — Uma distribuição Python por camada (5 pacotes, deps declaradas)
- O que é: `voicecoach-domain`, `voicecoach-application`, etc., cada um com seu
  `pyproject.toml` declarando de quem depende — reproduzindo literalmente o
  modelo de referências entre `.csproj`.
- Por que foi rejeitada: é a solução mais fiel ao mundo .NET e a mais cara.
  Cinco manifestos, cinco builds e um ciclo de versionamento interno para um
  projeto de uma pessoa — exatamente o overengineering que a Parte F da visão
  manda cortar. O `import-linter` entrega a mesma garantia sem fragmentar o
  empacotamento. Gatilho para reavaliar: se alguma camada precisar ser
  publicada e consumida de fora deste repositório.

### Alternativa D — Teste de arquitetura escrito à mão (pytest varrendo o AST)
- O que é: um teste que percorre os módulos com `ast` e falha em import proibido.
- Por que foi rejeitada: reimplementa mal o que o `import-linter` já faz (grafo
  transitivo, cache, mensagens com arquivo e linha). Código próprio para
  problema resolvido é dívida, não aprendizado.

## Consequências

**Positivas**
- A regra da visão §D vira verificação de ~0,3s, offline e a custo zero
  (ADR-0010), pronta para virar gate no CI (CARD-003).
- Violação vem com arquivo e linha: `voicecoach.domain -> fastapi (l.16)`.
- O contrato é documentação que não pode mentir — se divergir do código, quebra.
- Verificado por violação injetada e revertida no CARD-001, para os dois
  contratos principais: `domain -> fastapi` e `api -> worker`.

**Negativas — o preço aceito**
- Mais uma dependência de dev (`import-linter` + `grimp`).
- Os contratos `forbidden` **não se atualizam sozinhos**: dependência nova que
  não entrar na lista não é vigiada. Mitigação é convenção (mesmo commit), não
  automação — é o elo fraco desta decisão.
- `import-linter` enxerga apenas imports **estáticos**. `importlib.import_module`
  com nome montado em runtime escapa do grafo. Aceito: fábrica dinâmica de
  adapter deve ficar na composition root (`api`/`worker`), onde importar
  qualquer coisa já é legal.
- Proibir pydantic no `domain` custa conversão explícita entre entidade e
  schema nas bordas. É trabalho real, aceito em troca de um domínio que não
  depende do ciclo de release de um framework de validação. **Gatilho para
  reavaliar:** se a conversão virar boilerplate repetitivo em mais de três
  agregados, escrever ADR novo em vez de afrouxar o contrato em silêncio.

**Equivalente mental .NET:** `NetArchTest`/`ArchUnitNET` rodando no build. A
diferença é que lá eles são um reforço opcional sobre uma barreira que o
`.csproj` já garante; aqui eles **são** a barreira.
