# CARD-004 — Skill de arquitetura do projeto (derivada dos ADRs)

- **ID:** CARD-004 · **Épico:** Fase 0 — Fundação (executa P4 item 1)
- **Plataforma:** infra · **Esforço:** P · **Status:** backlog
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
