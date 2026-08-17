---
description: Cria um card de backlog no formato padrão em docs/backlog/
argument-hint: <descrição do card>
---

Crie um novo card de backlog a partir desta descrição: $ARGUMENTS

Regras:

1. Leia `docs/backlog/CARD-000-template.md` e siga o formato **exatamente** —
   todas as seções, incluindo "Objetivo de aprendizado" (obrigatório e
   específico, conforme o exemplo no template).
2. Determine o próximo ID sequencial olhando os arquivos existentes em
   `docs/backlog/` (CARD-001, CARD-002, ...).
3. Nome do arquivo: `CARD-XXX-titulo-kebab-case.md`.
4. O card deve caber em **uma sessão de trabalho**. Se a descrição implicar
   mais que isso, quebre em múltiplos cards e declare as dependências entre eles.
5. Critérios de aceite em formato Dado/Quando/Então, verificáveis por teste
   automatizado sempre que possível.
6. Se o card embutir uma decisão arquitetural (ver `docs/adr/README.md`),
   aponte isso na proposta técnica e referencie o ADR existente ou registre
   que um ADR precisa ser criado antes da implementação.
7. Se existir `docs/backlog/README.md` com a tabela consolidada, adicione a
   linha do novo card nela.
8. Ao final, mostre o card criado e pergunte se ajusto algo antes de considerar
   pronto.
