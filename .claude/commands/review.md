---
description: Revisa o diff atual contra o CLAUDE.md e a Definition of Done
argument-hint: [base opcional, ex. main ou um commit — padrão: mudanças não commitadas]
---

Revise as mudanças atuais contra a constituição do projeto.

Alvo da revisão: $ARGUMENTS (se vazio, use o diff não commitado — `git diff` +
`git diff --staged` + arquivos novos não rastreados; se um ref foi passado,
use `git diff <ref>...HEAD`).

Passos:

1. Leia `CLAUDE.md` (convenções + Definition of Done) e os ADRs em `docs/adr/`
   relacionados aos arquivos tocados. Se o diff toca `backend/`, carregue também
   a skill `voicecoach-arquitetura` — o checklist de PR dela é o insumo direto da
   seção "Risco arquitetural".
2. Analise o diff completo, não apenas os trechos alterados — uma mudança pode
   violar um invariante definido em outro lugar do arquivo.
3. Reporte os achados em **três seções separadas**:

   ## Risco arquitetural
   Violações de camadas, acoplamento indevido, decisão que contraria um ADR,
   decisão nova sem ADR (ver `docs/adr/README.md` para quando ADR é obrigatório).

   ## Risco funcional
   Bugs, casos de borda não tratados, comportamento que contraria os critérios
   de aceite do card em andamento, ausência de teste para comportamento novo.

   ## Risco de performance
   Chamadas externas sem timeout/retry, I/O síncrono em caminho async, trabalho
   desnecessário em hot path, impacto de custo (chamadas de LLM/STT/TTS a mais).

4. Para cada achado: severidade (crítica/alta/média/baixa), evidência
   (arquivo:linha) e correção sugerida.
5. Feche com um veredito contra a Definition of Done: itens atendidos e itens
   pendentes, um por um.
6. Não altere código nesta revisão — apenas reporte. Correções são tarefa
   separada, decidida por mim.
