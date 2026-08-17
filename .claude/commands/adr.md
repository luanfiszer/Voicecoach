---
description: Cria um ADR numerado em docs/adr/ com alternativas e trade-offs
argument-hint: <decisão a registrar>
---

Registre um Architecture Decision Record para esta decisão: $ARGUMENTS

Regras:

1. Leia `docs/adr/0000-template.md` e `docs/adr/README.md` antes de escrever.
2. Determine o próximo número sequencial olhando os arquivos existentes em
   `docs/adr/`. Nome do arquivo: `XXXX-titulo-kebab-case.md`.
3. **Mínimo de duas alternativas reais consideradas**, cada uma com o motivo
   objetivo da rejeição (trade-off, não preferência). Se você não consegue
   nomear duas alternativas sérias, a decisão provavelmente não precisa de ADR —
   diga isso em vez de inventar alternativas de palha.
4. A seção "Consequências" deve incluir consequências **negativas** — o custo
   aceito. ADR sem custo declarado está incompleto.
5. Quando aplicável, inclua o equivalente mental no mundo .NET (contexto do
   desenvolvedor no CLAUDE.md).
6. Status inicial: "proposto". Só marque "aceito" quando eu confirmar
   explicitamente.
7. Atualize a tabela de índice em `docs/adr/README.md`.
8. Ao final, apresente um resumo da decisão e dos trade-offs e pergunte se
   aceito, ajusto ou rejeito.
