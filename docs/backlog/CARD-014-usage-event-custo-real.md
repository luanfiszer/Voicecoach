# CARD-014 — UsageEvent: custo real por Turn

- **ID:** CARD-014 · **Épico:** Fase 2 — Proteção de custo
- **Plataforma:** backend · **Esforço:** P · **Status:** backlog
- **Dependências:** CARD-009

## Contexto

Visão §D: "a métrica de custo por usuário/sessão nasce no domínio". ADR-0010
depende de medição real para o teto fazer sentido. O diagnóstico calculou
custo por estimativa; agora ele vira dado por turn.

## Problema

Sem registro de uso real (tokens, segundos de áudio, chars de TTS), quota e
kill switch operariam no escuro.

## Proposta técnica

- Entidade/tabela `UsageEvent`: `turn_id, student_id, stt_seconds,
  llm_input_tokens, llm_output_tokens, tts_chars, provider/modelo de cada
  passo, estimated_cost_usd (Decimal)`.
- Tabela de preços por modelo em config (não literal no código — ADR-0009);
  adapters locais registram uso com custo 0 (o dado de volume continua
  valioso).
- Gravado pelo use case ao completar o turn (mesma transação).
- Query utilitária/endpoint dev: custo por dia e por student.
- Testes: cálculo com preços conhecidos; turn com STT local ⇒ custo só de
  LLM.

## Escopo

- **In:** o acima. **Out:** enforcement de quota/kill switch (CARD-015);
  dashboard (Fase 5).

## Critérios de aceite

- **Dado** um turn completado com Haiku (tokens conhecidos via mock),
  **então** o UsageEvent grava tokens e `estimated_cost_usd` bate com a
  tabela de preços (Decimal, teste exato).
- **Dado** STT/TTS locais, **então** custo desses passos = 0 e os volumes
  (segundos/chars) ainda são gravados.
- **Dado** 3 turns de 2 students, **então** a agregação por student soma
  certo.

## Riscos

Preços mudam — por isso ficam em config com data; o eval (Fase 4) reusa este
registro para a métrica de custo por interação.

## Objetivo de aprendizado

`Decimal` para dinheiro em Python (por que float quebra, contexto/quantize —
o paralelo do decimal do C#) e usage reporting dos SDKs de IA (onde os
tokens reais vêm na resposta).
