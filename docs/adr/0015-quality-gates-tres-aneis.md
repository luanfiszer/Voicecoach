# ADR-0015 — Quality gates em três anéis: agente, pre-commit e CI

- **Status:** aceito (item 3 ajustado por [ADR-0019](0019-limiar-global-de-cobertura-com-folga-agora-que-o-nucleo-morde.md))
- **Data:** 2026-08-18
- **Complementa:** ADR-0010 (política de custo), ADR-0012 (contratos de camada)
- **Critérios de obrigatoriedade** (`docs/adr/README.md`): **1 — introduz
  dependências externas** (`ruff`, `mypy`, `pytest-cov`, `pre-commit`,
  `gitleaks`) e **2 — define uma fronteira** (o que é bloqueante, onde bloqueia,
  e o que é apenas aviso).

## Contexto

O F12 do diagnóstico é o único achado marcado como **transversal**: o protótipo
não tem um teste nem um gate, e por isso "qualquer refatoração é feita às
cegas" — sendo que refatorar é o plano inteiro. O roadmap põe o critério de
saída da Fase 0 como "CI roda ruff+mypy+pytest e está verde; pre-commit ativo".

Há um agravante que o diagnóstico não podia prever: **este projeto é executado
sessão a sessão, com agente**. Um erro de estilo ou de tipo introduzido numa
sessão não é percebido na seguinte, porque a seguinte começa sem memória. Vale
aqui o mesmo raciocínio do ADR-0012 — regra que depende de alguém lembrar é
regra que erode.

Medição do estado real antes de decidir (`--with`, sem tocar no projeto):
`mypy --strict` → 2 erros; `ruff check` → 3; `ruff format` → 3 de 16 arquivos;
cobertura total → 70%, com `domain` e `application` em **zero statements**.

## Decisão

### Um gate, três anéis, do mais barato ao mais lento

| Anel | Quando roda | O que roda | Papel |
|---|---|---|---|
| **1. Agente** | a cada `Write`/`Edit` de `.py` em `backend/` (hook `PostToolUse` em `.claude/settings.json`) | `ruff format`, `ruff check --fix`, `mypy` | corrige o erro **no segundo em que nasce**; sai com código 2 para o erro voltar para a sessão |
| **2. pre-commit** | `git commit` | os do anel 1 + `gitleaks`, `lint-imports`, higiene de arquivo | impede que o erro entre na história |
| **3. CI** | push em `main` e todo PR | tudo do anel 2 + `pytest` + os dois anéis de cobertura + geração do OpenAPI | impede que o erro entre em `main` |

Os anéis são redundantes de propósito: cada um pega o que o anterior deixou
passar (`--no-verify` pula o anel 2; uma máquina sem `pre-commit install` pula
o anel 2 inteiro; só o anel 3 é inescapável).

### Ferramentas

1. **`ruff`** como formatter e linter, 88 colunas, alvo `py312`. O conjunto de
   regras é **curado, não mínimo**: além dos erros (`E`, `W`, `F`, `I`), entram
   as famílias que corrigem *idioma* (`UP`, `B`, `C4`, `SIM`, `PT`, `N`, `BLE`)
   e a que exige anotação de tipo (`ANN`). O critério é o do CLAUDE.md: o
   produto deste projeto é o conhecimento do desenvolvedor, e um linter que diz
   "em Python isso se escreve assim" é um revisor de idioma trabalhando de graça
   em cada arquivo.
2. **`mypy --strict`** sobre `src/` e `tests/`. Override por módulo é permitido
   quando a biblioteca não publica `py.typed` (hoje: `asyncpg`), sempre pontual
   e com o gatilho de remoção escrito ao lado. Afrouxar o modo global, não.
3. **Cobertura em dois anéis**: `--cov-fail-under=70` global (o valor **real**
   medido hoje, sem folga inventada — assim qualquer regressão quebra) e um
   segundo comando exigindo **90% de `domain` + `application`**. Hoje o segundo
   passa com zero statements; passa a morder no CARD-005.
4. **`pre-commit`** orquestrando os hooks, com `rev` fixo em todos os repos.
5. **`gitleaks`** varrendo o diff atrás de segredo.
6. **CI no GitHub Actions**, dois jobs: `backend` e `openapi`.

### Duas escolhas que não são óbvias

**Os hooks do backend rodam como `language: system`, via `uv run`** — não no
virtualenv isolado que o `pre-commit` criaria por padrão. Isolado, o `mypy` não
enxergaria `fastapi`, `pydantic` nem `httpx`, e cuspiria erro de import em
praticamente todo arquivo. Um gate que grita errado é um gate que se desliga na
primeira semana.

**O `mypy` roda com `pass_filenames: false`**, isto é, sobre o projeto inteiro,
e não sobre os arquivos do commit. Tipagem é propriedade do **grafo**, não do
arquivo: mudar a assinatura de uma função quebra quem a chama, e quem a chama
pode não estar no commit.

## Alternativas consideradas

### Alternativa A — `black` + `flake8` + `isort` (o conjunto clássico)
- O que é: o trio que o ecossistema Python usou por uma década.
- Por que foi rejeitada: três ferramentas, três configurações e três chances de
  discordarem entre si (o conflito `black` × `flake8` sobre E203 é folclore).
  `ruff` faz o trabalho das três, em Rust, no repositório inteiro em ~50 ms. O
  que se perde é honesto: plugins de `flake8` ainda não portados. Nenhum deles
  está no conjunto escolhido.

### Alternativa B — `pyright` em vez de `mypy`
- O que é: o type checker da Microsoft, mais rápido e com inferência melhor.
- Por que foi rejeitada: é distribuído em Node — colocaria a segunda toolchain
  do monorepo dentro do gate do Python, inclusive no `pre-commit`. E o
  ecossistema de bibliotecas publica stubs mirando `mypy`. **Gatilho para
  reavaliar:** se o tempo do `mypy` no anel 1 passar a incomodar, ou se
  aparecer erro que só o `pyright` entende.

### Alternativa C — Só CI, sem pre-commit nem hook
- O que é: um único gate, no fim.
- Por que foi rejeitada: o custo de corrigir cresce com a distância do erro.
  Descobrir uma anotação faltando 8 minutos depois, num log do GitHub, custa
  troca de contexto; descobrir no instante da edição custa nada. Além disso o CI
  é assíncrono — nesta configuração, o agente terminaria a sessão antes do
  resultado chegar.

### Alternativa D — Só pre-commit e hook, sem CI
- O que é: confiar nos anéis locais.
- Por que foi rejeitada: `git commit --no-verify` existe, e uma máquina que
  nunca rodou `pre-commit install` não tem gate nenhum. O anel que não pode ser
  pulado é o único que dá garantia sobre o que está em `main`.

### Alternativa E — `--cov-fail-under` com folga (ex.: 60% quando o real é 70%)
- O que é: deixar margem para não incomodar.
- Por que foi rejeitada: um limiar abaixo do valor real permite que a cobertura
  **caia** sem quebrar nada — é um gate que autoriza a regressão que deveria
  impedir. O número travado no valor de hoje sobe conforme os cards entregam
  teste; é disciplina, não teto.

### Alternativa F — Validador de arquitetura/estilo por LLM no PR
- Já rejeitada no ADR-0012 (custo recorrente por PR, contra o ADR-0010; e não
  determinístico). Registrada aqui porque a tentação reaparece a cada gate novo.

## Consequências

**Positivas**
- O F12 fecha: erro de estilo, de tipo, de arquitetura ou de segredo passa a ter
  três chances de ser barrado antes de `main`.
- O anel 1 dá ao agente o retorno que ele não teria sozinho — o erro volta na
  própria sessão, com o texto do `mypy`, e não numa sessão futura sem memória.
- Custo em dinheiro: **R$ 0**. Repositório público ⇒ Actions gratuito e
  ilimitado (ADR-0010); todas as ferramentas rodam offline.
- O conjunto curado do `ruff` funciona como material didático contínuo para
  quem está aprendendo o idioma.

**Negativas — o preço aceito**
- Cinco dependências de desenvolvimento a mais, e `rev`/versões para manter.
- O `mypy` no anel 1 acrescenta ~1–2 s a cada edição de arquivo Python.
- `ANN` obriga anotar tudo, inclusive testes — verbosidade real, em troca de o
  `mypy` ter o que checar (função sem anotação é função que ele ignora).
- O segundo anel de cobertura está **dormente**: hoje mede 100% de zero linhas.
  Só demonstra valor no CARD-005. Aceito conscientemente — o gate precisa
  existir *antes* do código que ele vigia, ou nasce negociando com o que já está
  lá.
- O job `openapi` precisa de uma `ANTHROPIC_API_KEY` descartável no ambiente,
  porque `create_app()` recusa subir sem ela (ADR-0013). Nenhuma chamada de rede
  ocorre; é um valor de fachada para o boot passar. Fica registrado porque um
  leitor futuro pode achar que há segredo de verdade no CI.

**Equivalente mental .NET:** `.editorconfig` com analyzers em
`TreatWarningsAsErrors`, `<Nullable>enable</Nullable>`, coverlet com threshold e
o mesmo conjunto rodando no pipeline. A diferença é que lá o compilador é um
gate que não se pode pular; aqui **todo** gate é opcional por natureza, e por
isso a redundância dos três anéis não é exagero — é o que substitui a barreira
de compilação.
