---
description: Explica um arquivo assumindo background C#/.NET, destacando idiomas Python sem paralelo
argument-hint: <caminho do arquivo>
---

Explique o arquivo: $ARGUMENTS

Contexto do leitor (do CLAUDE.md): desenvolvedor sênior C#/.NET, iniciante em
Python. Não explique conceitos de arquitetura (DI, repositório, camadas) —
explique **Python e seu ecossistema**.

Formato da explicação:

1. **Papel do arquivo** — o que ele faz no sistema, em 2-3 frases.
2. **Passeio pelo código** — bloco a bloco, na ordem do arquivo:
   - Para cada biblioteca usada: o que resolve, por que ela e não a alternativa
     comum, e o equivalente mental no mundo .NET (ex.: FastAPI ≈ ASP.NET Core
     Minimal APIs; pydantic ≈ record + FluentValidation).
   - Para cada idioma de Python **sem paralelo direto em C#** (context managers,
     decorators, generators, async sem Task, duck typing, protocols,
     dataclasses, descritores, `__dunder__`, comprehensions, `*args/**kwargs`),
     pare e explique em ~3 linhas: o que é, o que aconteceria sem ele, e o mais
     próximo que existe em C#.
3. **Armadilhas** — o que neste arquivo surpreenderia um dev .NET
   (mutabilidade, escopo, import side effects, GIL se relevante).
4. **Duas perguntas de verificação** — ao final, faça 2 perguntas sobre o
   arquivo para eu responder (regra do explicador do CLAUDE.md). Se eu errar,
   reexplique de outro jeito antes de seguir.
