# CARD-007 — Porta TeacherLlm + adapter Anthropic com saída estruturada validada

- **ID:** CARD-007 · **Épico:** Fase 1 — Fatia vertical
- **Plataforma:** backend/IA · **Esforço:** M · **Status:** backlog
- **Dependências:** CARD-002 (config/modelos); padrão de porta do CARD-006

## Contexto

O núcleo pedagógico portado do protótipo (`SYSTEM_PROMPT`, contrato JSON,
regras) — a parte listada como "preservar" no diagnóstico §7.1. ADR-0009/0010:
`TEACHER_MODEL` por config (Haiku em dev). O F9 do diagnóstico (fallback de
JSON inválido indo para TTS) morre aqui.

## Problema

O protótipo confiava em `json.loads` tolerante sobre texto livre; a versão
nova precisa de contrato garantido e histórico vindo de fora (não de dict
global — F5/F7).

## Proposta técnica

- Porta `TeacherLlm`: `respond(history: list[TurnExchange]) ->
  Result[TeacherFeedback, LlmError]` — o histórico **entra** (application/DB
  é dono dele; corrige F7 por desenho).
- `TeacherFeedback` como modelo pydantic: `has_mistakes, original, corrected,
  tip, spoken_reply, translation_pt` — validação estrita; falha de schema =
  `LlmError`, **nunca** texto cru adiante (mata F9).
- Prompt portado do protótipo para **arquivo versionado**
  (`prompts/teacher/v1.md` — pré-requisito do eval, P5), carregado no boot.
- Adapter Anthropic com SDK atual: timeout explícito curto, retries
  limitados (F8), structured output conforme SDK moderno.
- Testes: application com fake; adapter com resposta gravada (respx/mock).

## Escopo

- **In:** o acima. **Out:** persistir Corrections (CARD-013); CEFR/auxiliares
  (Fase 6); eval (Fase 4).

## Critérios de aceite

- **Dado** resposta do LLM fora do schema, **quando** validada, **então**
  retorna `LlmError` e o turn marca `failed` com motivo — nada vai para TTS.
- **Dado** um histórico passado pela application, **então** nenhum estado de
  conversa vive no adapter (inspecionável por teste de duas chamadas).
- **Dado** timeout configurado, **quando** o mock demora, **então** a chamada
  falha no prazo com erro tipado.

## Riscos

Definição do Result pattern acontece aqui na prática — se crescer, extrair
para ADR próprio antes de espalhar (regra do ADR README).

## Objetivo de aprendizado

Validação pydantic como fronteira anti-corrupção para saída de LLM, e o
primeiro Result caseiro em Python: `Union`/generics + pattern matching
(`match`) — o que o C# resolve com OneOf/switch expressions.
