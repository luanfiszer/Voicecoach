# Análise de referência — skill `medsoft-arquitetura` (C#/.NET)

- **Data:** 2026-08-18
- **Origem:** `~/.claude/skills/medsoft-arquitetura/` (skill pessoal do
  desenvolvedor, extraída do serviço de produção MEDSoft; `SKILL.md` 52 linhas +
  `REFERENCE.md` 206 linhas)
- **Motivação:** o CARD-004 pede uma skill de arquitetura que "espelha a skill
  que o desenvolvedor usa no projeto .NET". Antes de espelhar, revisar — o que
  vale copiar é a **forma**, e uma parte do conteúdo é armadilha.
- **Análise irmã:** [`analise-backend-medsoft-autorizacaoconteudos.md`](analise-backend-medsoft-autorizacaoconteudos.md),
  sobre o serviço; esta é sobre o artefato que descreve o serviço.

## O que foi lido

`SKILL.md` inteiro (mapa de camadas em 7 níveis, tabela "tipo → camada", "o que
NÃO fazer", checklist de PR) e `REFERENCE.md` inteiro (camadas em detalhe com
exemplos em C#, CQS, nomenclatura, pipeline Consumer→Component, soft delete,
comparações, e uma tabela final "Decisões registradas" datada).

---

## O que foi aproveitado

**1. A forma de dois arquivos.** `SKILL.md` curto e navegável — o que o agente
lê para decidir — e `REFERENCE.md` com o porquê, carregado só quando a decisão
exige contexto. É progressive disclosure aplicada a convenção, e resolve a
tensão real: a skill precisa ser curta para ser lida e longa para ser útil.

**2. A tabela "preciso de X → vai em Y".** É a pergunta que de fato aparece
("onde coloco isso?"), respondida por lookup em vez de por prosa. Foi copiada
como estrutura, com o conteúdo trocado por camadas Python + a coluna extra que
falta lá: **a fonte**.

**3. A seção "O que NÃO fazer" em imperativo.** Proibição escrita como proibição
é auditável; escrita como recomendação, é ignorável.

**4. O checklist de PR.** Transforma a skill em algo que se usa no fechamento,
não só na hora de escrever.

**5. A tabela "Decisões registradas" datada** — o item mais valioso, e o que o
primeiro rascunho da skill do Voicecoach tinha esquecido. É o que faz a skill
crescer por experiência: cada linha é uma decisão que foi tomada, com a data e o
motivo. Sem ela, a skill só pode crescer por antecipação, que é como skill vira
letra morta.

---

## O que foi recusado

**1. Todo o conteúdo .NET.** EF Core (`AsNoTracking`, `AsSplitQuery`,
`HasQueryFilter` para soft delete), `implicit operator` para converter entidade →
model, `.Equals()` em GUID, `protected set` + `Factory` estática. Nada disso tem
tradução: em Python o ORM é SQLAlchemy, a conversão é explícita, e a
imutabilidade é `@dataclass(frozen=True)`.

**2. A regra "Domain Service mora em Application, não em Domain".** Faz todo
sentido lá, e pelo motivo certo: o service precisa referenciar `Presentations`
(onde moram os DTOs), e `Domain` não pode referenciar `Presentations`. Só que
essa é uma consequência de uma camada que **não existe aqui** — o Voicecoach não
tem `Presentations`; schemas pydantic vivem na borda `api/` (ADR-0008). Importar
a regra importaria a solução de um problema que não temos, e ainda por cima
empurraria lógica pura para fora do `domain` sem motivo.

**3. Nomenclatura de tipo em português.** Lá é deliberado (`TrilhaTema`,
`ForcarConclusaoTemaService`), e a linguagem ubíqua do negócio é em português.
Aqui a linguagem ubíqua da visão §A já nasceu em inglês (`Student`, `Turn`,
`Correction`, `UsageEvent`) e o PEP 8 é imposto por `ruff` (`N`).

**4. A camada `Common`.** Lá é o depósito de utilitário transversal, com regra
explícita para não virar lixeira ("nome em português indica domínio, sai de
`Common`"). O backend tem cinco camadas e um `config.py`; criar uma sexta gaveta
"para o que não se encaixa" é convidar o que não se encaixa a existir. Se
aparecer utilitário sem dono, o certo é perguntar de que camada ele é.

---

## A crítica que mudou o desenho da skill do Voicecoach

**Nenhuma regra da skill MEDSoft cita fonte.** A tabela "Decisões registradas"
tem sete linhas com decisões arquiteturais de verdade — `NackDrop` → `NackRequeue`
nos consumers, dois commits intencionais no fluxo de sincronização,
`ProgressoSincronizacaoHelper` estático virando service — cada uma com um motivo
de uma linha e **nenhum documento por trás**. Não há alternativa considerada, não
há consequência negativa registrada, não há como saber se a decisão ainda vale.

O efeito prático: quando alguém discorda de uma regra, não existe o que
consultar. A skill vira a autoridade — e uma skill sem lastro é indistinguível de
opinião do agente escrita com confiança. É exatamente o erro do
[LEARNING-0003](../learnings/0003-item-de-adr-da-dod-marcado-sem-conferir-criterio.md):
decisão que ficou registrada no lugar errado (ali o card, aqui a skill) some do
radar de quem procura decisão.

Daí a regra estrutural da skill deste repositório: **nenhuma regra sem ADR de
origem**, e o log de mudanças da própria skill no fim do `REFERENCE.md`. A skill
não é onde a decisão nasce; é onde a decisão vira convenção operacional. É o que
torna a versão Python melhor que o original que a inspirou — não uma tradução
dele.

**Consequência para o outro lado:** vale levar esta crítica de volta ao MEDSoft.
Aquelas sete linhas mereciam ser sete ADRs curtos no repositório do serviço. Isso
está fora do escopo deste projeto — fica registrado como observação, não como
tarefa.

---

## Segunda diferença de fundo: a skill lá é reforço, aqui é barreira

No .NET, quase tudo que a skill pede já é imposto por outra coisa: o `.csproj`
impede a referência errada, o compilador impede o tipo errado, o analyzer pega o
resto. A skill orienta onde a ferramenta é silenciosa (nome, granularidade,
cenário de negócio).

Em Python, não existe barreira de compilação — e é por isso que aqui a divisão é
outra: **o que dá para tornar executável vira contrato** (`import-linter`,
`ruff`, `mypy` — ADR-0012 e ADR-0015), e a skill fica com o que sobra. Copiar a
proporção da skill MEDSoft, onde quase tudo é prosa, seria copiar a confiança
sem copiar a rede de proteção que a justifica.
