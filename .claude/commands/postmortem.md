---
description: Registra um erro em docs/learnings/ e propõe regra nova no CLAUDE.md
argument-hint: [descrição do erro — opcional, posso inferir do contexto da sessão]
---

Registre um post-mortem do erro: $ARGUMENTS

Se nenhuma descrição foi passada, identifique o erro a partir do contexto da
sessão atual (algo quebrou, foi revertido, ou o desenvolvedor apontou um erro
meu).

Regras:

1. **Pare qualquer implementação em andamento.** O post-mortem tem prioridade.
2. Leia `docs/learnings/0000-template.md` e siga o formato exatamente.
3. Determine o próximo número sequencial em `docs/learnings/`.
   Nome do arquivo: `XXXX-titulo-kebab-case.md`.
4. Vá até a **causa raiz** — não pare no sintoma reformulado. Pergunte "por quê"
   até chegar em algo acionável.
5. Proponha uma **regra nova para o CLAUDE.md** que impeça a recorrência:
   - Mostre o texto exato da regra e onde ela entraria.
   - Antes de adicionar, verifique se uma regra existente já cobre o caso ou
     se sobrepõe — nesse caso, proponha a **consolidação**, não uma regra a mais.
     O CLAUDE.md deve ficar mais rigoroso com o tempo, não maior à toa.
6. Só edite o CLAUDE.md depois que eu aprovar o texto da regra.
7. Ao final, resuma: sintoma → causa raiz → regra criada/consolidada.
