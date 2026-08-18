# CARD-004 — Skill de arquitetura do projeto (derivada dos ADRs)

- **ID:** CARD-004 · **Épico:** Fase 0 — Fundação (executa P4 item 1)
- **Plataforma:** infra · **Esforço:** P · **Status:** concluído
- **Dependências:** CARD-001, CARD-003

## Contexto

P4 item 1: codificar as convenções da codebase numa skill em
`.claude/skills/`, derivada dos ADRs 0002–0011 — não inventada. Espelha a
skill que o desenvolvedor usa no projeto .NET (medsoft-arquitetura).

## Problema

Sem a skill, cada sessão de implementação depende da memória do agente sobre
os ADRs — exatamente o que o harness quer eliminar.

## Proposta técnica

Skill `voicecoach-arquitetura` contendo: as camadas e o que é **proibido** em
cada uma (domain sem IO/framework; application sem SDK; portas como
`Protocol`); padrão de erro/Result adotado; nomenclatura (módulos, portas
`XxxPort`?, adapters); proibições explícitas (modelo SQLAlchemy fora de
adapters, pydantic fora da borda, literal de modelo de IA em código —
ADR-0009); checklist de review por PR. Cada regra cita o ADR de origem.

## Escopo

- **In:** a skill + gatilhos de uso descritos; regra no CLAUDE.md apontando
  para ela.
- **Out:** convenções ainda inexistentes (ex.: detalhes do Result — se o
  ADR não existir ainda, a skill marca TBD com referência ao card futuro).

## Critérios de aceite

- **Dado** uma pergunta "onde coloco X?", **quando** a skill é invocada,
  **então** a resposta sai das regras escritas, com ADR citado.
- **Dado** as regras da skill, **quando** comparadas aos ADRs 0002–0011,
  **então** nenhuma regra existe sem fonte.

## Riscos

Skill nascer grande demais e virar letra morta — começar mínima e crescer
com os postmortems (loop de aprendizado do P4).

## Objetivo de aprendizado

Praticar a destilação de ADRs em regras operacionais curtas — a habilidade
de transformar decisão em convenção cobrável (o que o CLAUDE.md chama de
"constituição" aplicada à arquitetura).

---

## Execução (2026-08-18)

### O ponto de partida: o rascunho já existia

A sessão não começou de folha em branco. `.claude/skills/voicecoach-arquitetura/`
já estava no working tree, **não rastreado** (209 linhas), redigido antes do
CARD-003. O trabalho real deste card foi, portanto, **auditoria**, não redação —
e a armadilha era commitar 209 linhas bem escritas sem conferir as que
envelheceram.

A auditoria regra a regra confirmou que **todas** tinham fonte real. As citações
mais arriscadas foram verificadas contra o texto do ADR:

| Regra da skill | Onde está escrito |
|---|---|
| dinheiro é `Decimal`, nunca `float` | ADR-0013, l.45 |
| porta evolui por extensão; descarte V1→V2 de ~15–20% | ADR-0003, l.22 e l.46 |
| lista `forbidden` não se atualiza sozinha ("elo fraco"); `importlib` escapa | ADR-0012, l.51 e l.106–108 |
| modelo de IA nunca literal, sempre config | ADR-0009, l.28 |
| SQLAlchemy só em `adapters`, domínio não importa | ADR-0004, l.19–22 |

O que estava **errado ou frágil**, e foi corrigido:

| # | Problema | Correção |
|---|---|---|
| P1 | Dizia "ruff/mypy/cobertura entram no CARD-003" e listava isso como lacuna TBD — o CARD-003 já tinha fechado | Seção "Quality gates" com o conteúdo do ADR-0015 (três anéis, dois anéis de cobertura, regra do `noqa`/`type: ignore`) |
| P2 | Copiava *verbatim* a lista de módulos `forbidden` do `pyproject.toml` — que muda no CARD-005 (`sqlalchemy`) e no CARD-007 (`anthropic`) | Cópia removida; ficou a **regra** ("mesmo commit") e o ponteiro para `[tool.importlinter]` |
| P3 | Duplicava `backend/README.md` sem hierarquia declarada | Tabela "Quem manda quando as fontes divergirem" no topo do `SKILL.md` |
| P4 | ADR-0002 não citado, embora o card mande cobrir 0002–0011 | Seção "Escopo": a skill é backend-only e cita o 0002 justamente para delimitar o que fica de fora |
| P5 | Faltava o que o card lista em "In": regra no `CLAUDE.md` e gatilhos; e faltava o log datado de decisões | Ambos adicionados |
| P6 | Citava `testcontainers`/`respx` como se existissem | Marcados *(planejado — ainda não instalados)* |

### O que foi entregue

- **`.claude/skills/voicecoach-arquitetura/SKILL.md`** (175 linhas): hierarquia
  de fontes, escopo, régua anti-overengineering, mapa de camadas, tabela "onde
  colocar o quê", proibições, convenções, quality gates, testes por camada e
  checklist de PR — **cada item com a fonte na própria linha**.
- **`.claude/skills/voicecoach-arquitetura/REFERENCE.md`** (256 linhas): o
  porquê de cada regra com o gatilho que a reabre, os equivalentes mentais .NET,
  as duas fugas conhecidas do import-linter, e o **log de decisões da própria
  skill** no fim.
- **`docs/referencias/analise-skill-medsoft-arquitetura.md`**: revisão crítica
  da skill .NET que serviu de modelo — o que foi aproveitado (forma de dois
  arquivos, tabela "preciso de X", checklist, log datado), o que foi recusado
  (conteúdo EF Core, "Domain Service em Application", nomenclatura em
  português, camada `Common`) e por quê.
- **`CLAUDE.md`**: nova regra de trabalho tornando a consulta à skill
  obrigatória antes de decidir camada, e a linha de `.claude/skills/` na tabela
  de artefatos do harness.
- **`.claude/commands/review.md`** e **`.claude/commands/executa-card.md`**:
  passam a carregar a skill (é o gatilho real — skill que não é invocada é
  letra morta, o risco que este card nomeia).

### A crítica que mudou o desenho (revisão da skill .NET)

A skill MEDSoft tem uma tabela "Decisões registradas" com sete decisões
arquiteturais reais (`NackDrop` → `NackRequeue`, dois commits intencionais no
fluxo de sincronização, helper estático virando service) — **nenhuma com
documento por trás**. Sem alternativa considerada, sem consequência negativa,
sem como saber se ainda valem. Quando alguém discorda, não há o que consultar:
a skill vira autoridade, e skill sem lastro é indistinguível de opinião do
agente escrita com confiança. É a mesma classe de erro do LEARNING-0003 —
decisão registrada no lugar errado some do radar de quem procura decisão.

Daí a regra estrutural desta skill: **nenhuma regra sem ADR de origem**, mais o
log de mudanças da própria skill. Foi o que se aproveitou de melhor da
referência: a forma, corrigindo a falha.

### Critérios de aceite — evidência

**Critério 1 — "onde coloco X?" responde a partir das regras, com ADR citado.**
A skill foi invocada de verdade, com uma pergunta que atravessa três camadas:
*"onde coloco o cálculo do custo em dólar de um Turn e o cliente HTTP que
consulta o preço?"*. Resposta produzida só a partir do texto carregado:

- cálculo → `domain/` (tabela "onde colocar o quê", ADR-0012), em `Decimal` e
  nunca `float` (ADR-0013);
- tabela de preços → `config.py`, chegando ao núcleo **por parâmetro**, porque
  `domain`/`application` não leem config (ADR-0013); preço em literal é o mesmo
  erro que modelo de IA em literal (ADR-0009);
- cliente HTTP → `adapters/`, porque `httpx` está no `forbidden` das duas
  camadas de dentro (ADR-0012), atrás de porta em `application/ports/` nomeada
  pela capacidade e sem sufixo `Port` (visão §D);
- orquestração → handler CQS em `application`, chamado pelo worker (ADR-0005);
- **e a objeção**: consultar preço por HTTP em runtime é peça nova para um
  número que muda uma vez por semestre — a visão §F manda deixar em `config.py`
  até haver gatilho.

**Critério 2 — nenhuma regra sem fonte, comparada aos ADRs 0002–0011.**
Auditoria mecânica, com a saída real:

```
### 1. Todo ADR citado existe em docs/adr/
  OK    ADR-0001 … ADR-0015     (15 citações, 15 arquivos encontrados, 0 falta)

### 2. ADRs 0002-0011 (faixa do card) ausentes:
  -> nenhuma linha acima = os dez estão citados

### 3. Regra sem fonte na própria unidade (bullet ou linha de tabela):
  unidades de regra verificadas: 47 | sem fonte declarada: 5
```

As 5 são 2 cabeçalhos de tabela e as 3 linhas da tabela "quem manda quando as
fontes divergirem" — que é meta-regra sobre a própria skill, não regra de
arquitetura. A primeira rodada da auditoria acusou 15 sem fonte; a correção foi
citar o ADR em cada item do checklist de PR (onde o agente age) e trocar
`| 0004 |` por `| ADR-0004 |` na tabela de infraestrutura, para que a citação
seja verificável por grep e não só por leitura.

**O achado: `pydantic` faltava no contrato de `application`.**
Ao demonstrar, para a regra do explicador, *por que* uma lista `forbidden`
desatualizada é pior que um gate vermelho, a demonstração encontrou o problema
real em vez de um hipotético. Duas violações no mesmo arquivo de `application`:

```
import httpx                     -> BROKEN
                                    voicecoach.application.violacao_demo -> httpx (l.1)
from pydantic import BaseModel   -> Contracts: 4 kept, 0 broken.
```

`pydantic` estava na lista de `domain`, mas **não** na de `application` — e a
regra "pydantic só na borda `api/`" (ADR-0008) existia na skill, no
`backend/README.md` e no docstring da camada, em lugar nenhum executável. O
CARD-005 é justamente onde um `BaseModel` de DTO de caso de uso apareceria, e
teria entrado com o CI verde.

Corrigido no mesmo commit deste card, com a prova de que o gate agora morde:

```
### injetando 'from pydantic import BaseModel' em application/:
  application não conhece framework nem SDK de provider BROKEN
  Contracts: 3 kept, 1 broken.
  voicecoach.application is not allowed to import pydantic:
  -   voicecoach.application.violacao_demo -> pydantic (l.1)

### revertido:
  Contracts: 4 kept, 0 broken.
```

**Sem ADR novo**, e o critério foi conferido: a mudança não *define* fronteira
(critério 2) — ela torna executável uma fronteira já decidida no ADR-0008 — nem
contraria convenção (critério 6): é exatamente a regra de manutenção que o
ADR-0012 estabelece ("dependência que não pode vazar para dentro entra na lista").
Ficou registrada no log de decisões da skill.

**A dívida que ele deixa:** o contrato continua sendo **denylist**, então a
classe do problema segue de pé — só esta instância foi fechada. A cura seria
inverter para allowlist (`application` só importa stdlib + `voicecoach.domain`),
possível no import-linter via contrato customizado. É decisão com trade-off real
(atrito a cada dependência legítima) e portanto ADR próprio, com gatilho: a
segunda vez que uma dependência entrar em camada errada sem o gate acusar.

**Gates (não-regressão — fora a linha do contrato, o card não toca código Python):**

```
16 files already formatted
All checks passed!
Success: no issues found in 16 source files
Contracts: 4 kept, 0 broken.
Required test coverage of 70% reached. Total coverage: 70.08%
4 passed in 0.05s
```

A prova de que o gate morde foi feita para o contrato alterado (bloco do achado
acima): violação injetada, quebra com arquivo e linha, revertida. Para os demais
gates ela não se repetiu — foi feita no CARD-001 e no CARD-003, e nenhum outro
arquivo `.py` mudou aqui.

### Item de ADR (LEARNING-0003)

Conferido contra a lista "Quando um ADR é OBRIGATÓRIO" de `docs/adr/README.md`,
critério a critério: **1 (dependência)** não — nenhuma dependência nova;
**2 (fronteira)** não — a skill *destila* fronteiras já decididas nos ADRs
0004/0008/0012/0013, sem criar nenhuma; **3 (custo)** não; **4 (segurança)**
não; **5 (difícil de reverter)** não — são dois markdown; **6 (contraria
convenção)** não.

Ressalva honesta: a decisão genuinamente nova desta sessão é a **hierarquia de
fontes** (`pyproject` > ADR > README > skill). Ela não se encaixa em nenhum dos
seis critérios — não é fronteira de código, dependência, custo nem segurança —,
então fica registrada na própria skill e aqui, e não em ADR. Se ela vier a ser
contestada, o critério 6 passa a valer e aí vira ADR.

### Regra do explicador — registro honesto

As duas perguntas foram feitas: (1) o que `Protocol` faz que dispensa Moq, e em
que momento se descobre que um fake não satisfaz a porta; (2) qual falha o
`lint-imports` **não** pega quando a lista `forbidden` fica desatualizada, e por
que isso é pior que um gate vermelho.

Nenhuma foi respondida — a primeira veio errada (CORS, que é política de origem
do browser e acontece depois, sobre HTTP; aqui o erro é de type-check, antes de
qualquer execução) e a segunda como "não sei dizer". As duas foram então
explicadas com demonstração executável em vez de prosa: um `Protocol` com três
fakes (um válido, um com método renomeado, um com tipo de retorno errado) reprovado
pelo `mypy --strict`, e as duas violações lado a lado em `application` mostrando
`BROKEN` para `httpx` e `4 kept, 0 broken` para `pydantic`.

**O item fica marcado como parcial, não cumprido:** a explicação foi entregue e
gerou correção real no repositório (o achado do `pydantic`), mas a verificação
de que o desenvolvedor consegue defender os dois pontos sozinho foi dispensada
por ele nesta sessão. Fica como gatilho para o CARD-005, que é onde os dois
assuntos voltam na prática — o primeiro `Protocol` de verdade (CARD-006) e a
primeira dependência nova entrando numa lista `forbidden` (`sqlalchemy`).

### Dívidas explícitas

| Dívida | Quem resolve |
|---|---|
| Skill de arquitetura do **cliente** (Expo/web, ADR-0002, 0007, 0008) | **CARD-011**, quando existir tela de verdade para conferir a regra contra ela. Escrevê-la agora seria regra sobre código inexistente (visão §F) |
| **Result pattern** continua TBD na skill — a visão §D cita `Result` em `application`, mas a forma em Python não foi decidida | CARD-005 em diante, no primeiro caso de uso real, e vira ADR ali |
| **Nome dos adapters concretos** sem convenção (a visão só fixa o nome das portas) | CARD-006/007/008; o que eles estabelecerem entra no log da skill |
| Contrato de camada segue **denylist**: só a instância do `pydantic` foi fechada, não a classe do problema | ADR próprio para inverter em allowlist, com gatilho: a segunda vez que uma dependência entrar em camada errada sem o gate acusar |
| A skill **não tem anel de verificação automática** — nenhum linter lê markdown | Deliberado (visão §F). A mitigação é a hierarquia de fontes, o não-copiar valor volátil e o item de checklist "regra que não bateu vira ADR". A auditoria por grep desta sessão pode virar script se a skill começar a divergir na prática |
