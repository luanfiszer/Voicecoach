# CARD-003 — Quality gates: ruff, mypy estrito, pytest, pre-commit, gitleaks, CI

- **ID:** CARD-003 · **Épico:** Fase 0 — Fundação (executa P4 itens 2–3)
- **Plataforma:** infra · **Esforço:** M · **Status:** concluído (2026-08-18)
- **Dependências:** CARD-001

## Contexto

O diagnóstico (F12) apontou zero testes e zero gates. O P4 do harness pede
gates automatizados + hooks do Claude Code, para a qualidade não depender de
disciplina. Este card executa essa sessão na prática.

## Problema

Sem gates desde o primeiro card de feature, cada sessão seguinte acumula
dívida invisível — e o Definition of Done do CLAUDE.md fica incobrável.

## Proposta técnica

- **ruff** (lint+format, substitui black/flake8/isort — ≈ dotnet format +
  analyzers) e **mypy --strict** no `backend/` (≈ nullable enable + analyzers
  em warning-as-error).
- **pytest** com layout `tests/{domain,application,adapters,api}` espelhando
  camadas; cobertura mínima nas camadas domain/application (fail under N%).
- **pre-commit**: ruff, mypy, gitleaks (secrets), end-of-file/trailing.
- **GitHub Actions**: job backend (uv sync → ruff → mypy → pytest) + job de
  geração de tipos OpenAPI (placeholder até CARD-010 gerar schema real).
- **Hooks do Claude Code** (P4 item 3): PostToolUse rodando ruff+mypy nos
  arquivos Python editados, para o agente corrigir antes de devolver a tarefa.
- Atualizar Definition of Done no CLAUDE.md: "quality gates passam
  localmente" vira item verificável.

## Escopo

- **In:** tudo acima configurado e rodando verde no repo atual.
- **Out:** skill de arquitetura (CARD-004); gates dos apps JS (entram com os
  apps, Fases 1 e 5).

## Critérios de aceite

- **Dado** um arquivo Python com erro de tipo, **quando** `git commit`,
  **então** o pre-commit bloqueia.
- **Dado** um push, **quando** o CI roda, **então** ruff+mypy+pytest executam
  e o pipeline fica verde no estado atual.
- **Dado** uma edição de arquivo Python pelo agente, **então** o hook roda
  lint/type check e devolve erros na sessão.

## Riscos

mypy strict sobre SQLAlchemy exige plugins/typing cuidadoso — aceitar
overrides pontuais documentados em vez de afrouxar o modo global.

## Objetivo de aprendizado

Mapear a toolchain: por que ruff substituiu três ferramentas (e o que perde),
o que `--strict` do mypy realmente liga, e como pre-commit difere de CI
(gate local vs gate de integração) — o paralelo com analyzers +
warning-as-error + pipeline do mundo .NET.

---

## Execução (2026-08-18)

### Medição antes de decidir

O estado real foi medido com `uv run --with <ferramenta>` (ambiente efêmero,
sem tocar no `pyproject.toml`) **antes** de propor qualquer configuração:

| Ferramenta | Resultado no código do CARD-002 |
|---|---|
| `mypy --strict` | 2 erros — `asyncpg` sem `py.typed`, e `conn` virando `Any \| None` |
| `ruff check` | 3 erros, todos `BLE001` (`except Exception`), os três deliberados |
| `ruff format` | 3 de 16 arquivos seriam reformatados |
| `pytest --cov` | 70% total; `domain` e `application` com **zero statements** |

Esse último número definiu o desenho do gate de cobertura.

### O que foi entregue

- **`backend/pyproject.toml`**: `[tool.ruff]` (88 colunas, `py312`, conjunto
  curado `E W F I N UP B BLE C4 SIM PT ANN RUF`), `[tool.mypy]` (`strict`, com
  override documentado para `asyncpg`), `[tool.coverage]` e `addopts` do pytest
  com `--strict-markers --strict-config`.
- **`.pre-commit-config.yaml`** (raiz): higiene de arquivo, `gitleaks`, e os
  gates do backend como `language: system` via `uv`.
- **`.gitleaks.toml`** (raiz): regras próprias para a chave da Anthropic — ver
  "o achado" abaixo.
- **`.github/workflows/ci.yml`**: job `backend` (ruff format, ruff check, mypy,
  lint-imports, pytest + 2 anéis de cobertura) e job `openapi` (gera o schema e
  publica como artefato).
- **`.claude/settings.json`** (versionado): hook `PostToolUse` em `Write|Edit`
  que roda `ruff format`, `ruff check --fix` e `mypy`, saindo com código 2 para
  o erro voltar para a sessão.
- **`CLAUDE.md`**: a seção "Convenções de código" sai do TBD (formatação,
  tipagem, nomenclatura, regra de supressão); a DoD ganha o item verificável de
  gates e o limite de 90% no núcleo.
- **`backend/src/voicecoach/adapters/health.py`**: os 2 erros de mypy
  resolvidos e os 3 `# noqa: BLE001` justificados.

### O achado que quase virou um gate decorativo

Ao tentar **provar** que o hook de segredo morde, uma chave `sk-ant-...` colada
num arquivo **passou pelo gitleaks sem um aviso**. O commit só foi barrado
porque o `ruff` reclamou do comprimento da linha — coincidência, não gate.

Investigação com o binário do próprio hook, contra cinco formatos:

```
$ gitleaks detect --no-git --source . --report-format json ...
  github-pat                          -> ghp_016C7e42...        (mascarado aqui)
  slack-bot-token                     -> xoxb-2635942...        (mascarado aqui)
total: 2 vazamentos          # a chave da Anthropic NÃO estava entre eles
```

> As amostras acima aparecem truncadas de propósito: na primeira tentativa de
> commitar este próprio card, o gitleaks **barrou o commit** porque as strings
> completas estavam coladas aqui. O gate funcionando contra quem o instalou é a
> melhor evidência que ele podia dar de si mesmo.

As regras de fábrica do gitleaks v8.30 não reconhecem `sk-ant-...` — e, pelo
ADR-0010, essa é a **única** credencial paga do projeto. O gate estava verde
exatamente no caso que importa. Daí o `.gitleaks.toml` com duas regras próprias
(uma por variante `api`/`admin`/`sid`, uma mais larga para mudança de prefixo) e
allowlist do `.env.example`.

**A lição, maior que o bug:** "o hook rodou e passou" não é evidência de que ele
protege. Só a violação injetada é.

### Item de ADR resolvido contra critério escrito

Consultada a lista **"Quando um ADR é OBRIGATÓRIO"** de `docs/adr/README.md`
(regra do LEARNING-0003). Aplicam-se dois critérios, e o resultado é o
[**ADR-0015**](../adr/0015-quality-gates-tres-aneis.md):

| Critério | Como se aplica |
|---|---|
| **1 — introduz dependência externa** | `ruff`, `mypy`, `pytest-cov`, `pre-commit`, `gitleaks` |
| **2 — define ou altera uma fronteira** | o que é bloqueante, em qual anel, e o que é apenas aviso |

O precedente é o próprio ADR-0012, que nasceu de uma dependência de
desenvolvimento (`import-linter`).

Quatro decisões não cobertas por ADR foram levadas ao desenvolvedor **antes** da
implementação: abrangência do ruleset do ruff, desenho do gate de cobertura,
destino da skill untracked e se o CLAUDE.md sairia do TBD.

### Evidência dos critérios de aceite

**Critério 1 — "arquivo Python com erro de tipo ⇒ o pre-commit bloqueia".**

```
$ git commit -m "isto nao deveria passar"
mypy --strict (backend)..................................................Failed
- hook id: mypy
- exit code: 1

src/voicecoach/domain/_gate_probe.py:5: error: Incompatible return value type
  (got "int", expected "str")  [return-value]
Found 1 error in 1 file (checked 17 source files)

$ git log --oneline -1
df797cc CARD-003: quality gates em três anéis   # o commit NÃO aconteceu
```

E com o segredo (após a regra própria):

```
$ git commit -m "isto definitivamente nao deveria passar"
Detect hardcoded secrets.................................................Failed
- hook id: gitleaks
RuleID:      anthropic-api-key
Entropy:     5.720891
File:        docs/_leak_probe.md
```

**Critério 2 — "no push, o CI roda ruff+mypy+pytest e fica verde".**

**Parcialmente verificado, e digo o que falta.** O workflow foi validado
localmente comando a comando (todos verdes, saída abaixo) e sintaticamente pelo
hook `check-yaml`. O passo mais arriscado — gerar o OpenAPI, que precisa de
`ANTHROPIC_API_KEY` porque `create_app()` recusa subir sem ela — foi executado
com a mesma chave descartável do CI:

```
$ ANTHROPIC_API_KEY=ci-nao-e-uma-chave-real uv run python -c "...create_app().openapi()..."
paths: ['/health', '/health/ready']
titulo: Voicecoach API 0.1.0
bytes: 2399
```

**O que não foi verificado:** o pipeline rodando de fato no GitHub Actions.
Depende de push, que o protocolo do card não autoriza sem consulta. Enquanto o
PR não rodar, este critério está *provado localmente, não em CI*.

**Critério 3 — "edição de arquivo Python pelo agente ⇒ o hook devolve os erros
na sessão".**

Duas provas. Formatação, com `ASGITransport( app = app )` introduzido via
`Edit` — o hook corrigiu sozinho para `ASGITransport(app=app)`. E tipo, com
`_elapsed_ms` mudando de `-> int` para `-> str`:

```
PostToolUse:Edit hook blocking error:
src/voicecoach/adapters/health.py:40: error: Incompatible return value type
  (got "int", expected "str")  [return-value]
src/voicecoach/adapters/health.py:72: error: Argument "latency_ms" ... [arg-type]
  ... (mais 5)
Found 7 errors in 1 file (checked 16 source files)
```

Sete erros para uma linha alterada.

**Correção de uma afirmação errada desta mesma seção.** Na primeira redação eu
escrevi que "seis deles estão nos chamadores" e que isso demonstrava o
`pass_filenames: false`. Está errado: o `mypy` reportou `Found 7 errors in 1
file` — os sete estão em `health.py`, o próprio arquivo editado. Aquilo mostra
propagação **dentro** do arquivo, não entre arquivos, e portanto não prova nada
sobre checar o projeto inteiro.

A evidência correta exige quebrar algo que atravessa a fronteira. Renomeando o
campo `up` do `DependencyStatus` (em `adapters/`):

```
tests/api/test_health.py:43: error: Unexpected keyword argument "up" ... [call-arg]
  ... (mais 4)
src/voicecoach/api/routes/health.py:53: error: "DependencyStatus" has no attribute "up"  [attr-defined]
src/voicecoach/api/routes/health.py:61: error: "DependencyStatus" has no attribute "up"  [attr-defined]
Found 14 errors in 3 files (checked 16 source files)
```

**Um arquivo alterado, 14 erros em 3 arquivos** — e os outros dois não foram
tocados. Um hook que recebesse só os nomes do commit teria checado `health.py`,
não encontrado nada de errado nele, e deixado passar a quebra em `api/` e nos
testes. É isso que o `pass_filenames: false` compra: tipagem é propriedade do
grafo de chamadas, não do arquivo.

**O gate de cobertura, os dois anéis.** Com um módulo de domínio sem teste:

```
### anel 1 (global, 70%)
FAIL Required test coverage of 70% not reached. Total coverage: 60.54%

### anel 2 (núcleo, 90%)
src/voicecoach/domain/_cobertura_probe.py      14     14      6      0     0%
Coverage failure: total of 0 is less than fail-under=90
EXIT=2
```

E com o teste presente, o mesmo código passa — o gate mede, não bloqueia por
princípio:

```
src/voicecoach/domain/_cobertura_probe.py      14      0      6      0   100%
EXIT=0
```

**Estado final, tudo verde e working tree limpo:**

```
$ uv run ruff format --check src tests   -> 16 files already formatted
$ uv run ruff check src tests            -> All checks passed!
$ uv run mypy                            -> Success: no issues found in 16 source files
$ uv run lint-imports                    -> Contracts: 4 kept, 0 broken.
$ uv run pytest --cov --cov-fail-under=70
   Required test coverage of 70% reached. Total coverage: 70.08%
   4 passed
$ uv run pre-commit run --all-files      -> os 11 hooks Passed
```

### Contratos de arquitetura

`4 kept, 0 broken`. **Nenhum contrato mudou neste card, e isso é intencional:**
as cinco dependências novas são todas de desenvolvimento e nenhuma é importada
pelo código — o `forbidden` do ADR-0012 vigia import, e não existe import a
vigiar. Foram os probes de cobertura (módulos reais em `domain/`) que
exercitaram o contrato de camada e continuaram verdes, como deviam: eles usavam
apenas `dataclasses`.

### Regra do explicador — status honesto

As 2 perguntas foram feitas (o `pass_filenames: false` do hook de mypy; o
limiar de cobertura travado no valor real). O desenvolvedor **não respondeu** —
pediu para seguir para o próximo card. O item da DoD, portanto, **não foi
cumprido por verificação nem pelo caminho alternativo da explicação**: foi
dispensado por decisão explícita do desenvolvedor, e fica registrado como tal
em vez de marcado como verde.

**É a terceira vez seguida.** CARD-001: perguntas feitas, desenvolvedor pediu a
explicação em vez de responder. CARD-002: "não sei responder", fechado por
explicação. CARD-003: dispensado. Três ocorrências não são coincidência — a
regra do explicador, como está escrita, não está produzindo o que o CLAUDE.md
diz ser o produto do projeto. **Gatilho:** rodar `/postmortem` sobre o próprio
mecanismo antes do CARD-005, e ajustar a regra (por exemplo: perguntas mais
curtas e no meio da implementação, e não um bloco no fim, quando a sessão já
está longa).

A pergunta 1, aliás, partia de uma leitura errada minha da saída do `mypy` —
corrigida na seção de evidências acima. Errar a premissa da pergunta é mais um
argumento para revisar o mecanismo.

### Dívidas registradas

- **CI não observado rodando** — critério 2 provado localmente, não no GitHub.
  **Gatilho:** o primeiro PR desta branch.
- **Segundo anel de cobertura dormente** — mede 100% de zero linhas.
  **Gatilho:** CARD-005, o primeiro código de domínio de verdade.
- **Job `openapi` é placeholder** — gera e publica o schema, mas não gera tipos
  TypeScript nem compara com o anterior para acusar breaking change.
  **Gatilho:** CARD-010 (primeira rota `/v1`), conforme ADR-0008.
- **O hook do anel 1 só vê `Write`/`Edit`** — arquivo alterado por comando de
  shell escapa dele (os anéis 2 e 3 continuam pegando).
- **`tests/{domain,application,adapters}` não foram criados** — a proposta do
  card previa o layout completo espelhando as camadas, mas isso colidiria com a
  regra do CARD-001 ("não antecipa pasta vazia sem dono"). A convenção está
  documentada; cada pasta nasce com seu primeiro teste. Prevaleceu a regra já
  estabelecida.
- **Testcontainers não entrou** — não estava no In deste card. A dívida do
  CARD-002 que apontava para cá **estava errada** e foi corrigida lá: o gatilho
  certo é o CARD-005.
- **`# type: ignore[call-arg]` em `Settings()` permanece** — o `warn_unused_ignores`
  do modo estrito confirma que ainda é necessário. **Gatilho:** avaliar o plugin
  do pydantic para mypy quando houver um segundo caso.
- **Gates dos apps JS não existem** — fora do escopo (Out do card); entram com
  os apps, nas Fases 1 e 5.
- **A skill `.claude/skills/voicecoach-arquitetura` continua untracked** — é o
  entregável do CARD-004 e não foi tocada aqui. Ela ainda não cita os ADRs 0013,
  0014 e 0015.
