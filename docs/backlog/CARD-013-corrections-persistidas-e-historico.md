# CARD-013 — Corrections tipadas persistidas + histórico do LLM vindo do banco

- **ID:** CARD-013 · **Épico:** Fase 2 — Domínio pedagógico
- **Plataforma:** backend · **Esforço:** M · **Status:** backlog
- **Dependências:** CARD-009, CARD-010

## Contexto

Visão §A: Correction é a entidade mais valiosa do produto (`tipo, trecho
original, forma correta, explicação, severidade`). Até aqui o feedback só
transita; agora vira dado. E o histórico do LLM passa a ser lido do banco
(mata de vez o estado em memória — F5/F7).

## Problema

O `TeacherFeedback` do CARD-007 traz correção em campo texto (herança do
protótipo); falta tipificar, persistir e reconstruir o contexto da conversa
a partir de Turns persistidos.

## Proposta técnica

- Evoluir o contrato do prompt (`prompts/teacher/v2.md`) para retornar
  `corrections[]` tipadas (type: grammar|vocabulary|preposition|word_order|
  other, original_excerpt, corrected_form, explanation, severity) — mantendo
  as regras pedagógicas (conservador, uma dica).
- **`severity` é enum fechado, não texto livre** (ajuste do CARD-005, sessão de
  reconciliação com as telas): a UI apresenta severidade em **palavras**
  ("pequeno ajuste", "vale revisar"), o que só é traduzível a partir de uma
  escala pequena e estável. Definir os níveis aqui, no domínio; o rótulo em
  pt-BR é apresentação e mora no cliente (CARD-016).
- Entidade `Correction` no domínio + tabela + repositório; Turn 1-N
  Correction.
- Histórico do `TeacherLlm` construído pela application a partir dos últimos
  N Turns da Session (equivalente do `_trim` do protótipo, agora por query).
- `GET /v1/turns/{id}` passa a incluir `corrections[]`; tipos regenerados.
- Testes: mapeamento prompt→entidades; reconstrução de histórico com N+2
  turns (corta certo); roundtrip de persistência.

## Escopo

- **In:** o acima. **Out:** UI (CARD-016); agregações/ErrorPattern (gatilho
  pós-MVP); eval do novo prompt (Fase 4 — mudança aqui é a última sem
  baseline, registrada como risco consciente).

## Critérios de aceite

- **Dado** uma resposta do LLM com 2 correções, **então** 2 Corrections
  persistem ligadas ao Turn, com enum de tipo válido.
- **Dado** uma Session com 12 turns e janela de 10, **então** o histórico
  enviado ao LLM contém exatamente os 10 últimos (teste).
- **Dado** o contrato novo, **então** os tipos gerados mudam e o app compila
  após atualização (verificado no CI).

## Riscos

Mudar prompt sem eval (Fase 4 ainda não existe) — mitigação: manter v1 e v2
lado a lado em `prompts/` e comparar manualmente com casos fixos; o eval
formaliza depois.

## Objetivo de aprendizado

Relacionamentos no SQLAlchemy 2.0 async: `relationship` + `selectinload` vs
lazy loading (que não existe de graça no async), e a decisão consciente de
carregamento por caso de uso — o contraste com o Include do EF.

## Ajuste da reconstrução (2026-08-19)

**Mantido, e movido para depois da proteção de margem** (era Fase 2, agora vem
após CARD-014/015). O motivo é sequenciamento, não mérito: o produto precisa
sobreviver comercialmente antes de ficar mais pedagógico, e a margem no usuário
pesado é de 1,49× (análise de custo §5).

**Um cuidado novo:** ao evoluir o contrato do prompt para `corrections[]`
tipadas, a **ordem dos campos do [ADR-0022](../adr/0022-ordem-dos-campos-da-resposta-do-professor-e-contrato-de-latencia.md)
não se mexe** — `spoken_reply` continua primeiro. É o tipo de regra que se perde
numa reescrita de prompt, e o teste do CARD-007 é o que a segura.
