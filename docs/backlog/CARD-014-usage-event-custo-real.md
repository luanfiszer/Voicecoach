# CARD-014 — UsageEvent: custo real por Turn (antecipado — é o instrumento de tudo)

- **ID:** CARD-014 · **Épico:** Fase 2 — Proteção de margem
- **Plataforma:** backend · **Esforço:** P · **Status:** backlog
- **Dependências:** CARD-009

## Contexto

Visão §D: *"a métrica de custo por usuário/sessão nasce no domínio"*. Com a
monetização confirmada (2026-08-19), este card deixa de ser higiene e vira
**instrumento de negócio**: é ele que diz se a margem existe.

## Por que agora

**Antecipado.** Três razões medidas:

1. **É pré-requisito do kill switch** (CARD-015), que é bloqueante de
   lançamento comercial — sem registro de uso, quota opera no escuro.
2. **100% do custo variável é o LLM** (~US$ 0,004/turn, meio a meio entre
   entrada e saída — análise de custo §2). O que não for medido aqui não é
   medido em lugar nenhum.
3. **É o detector de mudança de regime do prompt caching.** O ADR-0021 adiou o
   caching porque o limiar medido é 4.096 tokens e a conversa não chega lá — mas
   se o histórico crescer, ele passa a valer, e **nada avisa**. Registrar as três
   contagens de entrada é o que transforma isso em dado observável.

## Problema

Sem registro de uso real (tokens, duração de áudio, chars de TTS), quota, kill
switch e precificação seriam palpite.

## Proposta técnica

- Entidade/tabela `UsageEvent`: `turn_id, student_id, stt_seconds,
  llm_input_tokens, llm_output_tokens, tts_chars`, provider/modelo de cada
  passo, `estimated_cost_usd` (`Decimal`).
- **As três contagens de entrada, separadas** (ADR-0021):
  `llm_input_tokens`, `llm_cache_creation_tokens`, `llm_cache_read_tokens`.
  Hoje as duas últimas são sempre 0 — e é justamente por isso que precisam
  existir: o dia em que deixarem de ser é o gatilho de reabrir o caching. Escrita
  de cache custa **1,25×** e, com prefixo volátil, sai **~25% mais caro** que não
  usar cache (medição §5.3) — errar não é perder desconto, é pagar multa.
- **Contagem de turns por janela**, não só minutos: é o driver de custo real
  (análise de custo §8), e o CARD-015 precisa dela para decidir a unidade da cota.
- Tabela de preços por modelo em config, com data (ADR-0009).
- Gravado pelo use case ao completar o turn, **na mesma transação**.
- Query utilitária: custo por dia, por student e **por turn** — as três visões
  que a decisão de cota exige.

## Escopo

- **In:** entidade, tabela, cálculo, registro, query.
- **Out:** enforcement (CARD-015); entitlement por plano (CARD-023); dashboard.

## Critérios de aceite

- **Dado** um turn com Haiku (tokens conhecidos via mock), **então** o
  `UsageEvent` grava tokens e `estimated_cost_usd` bate com a tabela de preços
  (`Decimal`, teste exato).
- **Dado** STT/TTS locais, **então** o custo desses passos é 0 e os volumes
  (segundos, chars) ainda são gravados.
- **Dado** uma resposta sem cache, **então** as três contagens são gravadas com
  `cache_read = 0` — o valor 0 é dado, não ausência.
- **Dado** 3 turns de 2 students, **então** a agregação por student soma certo,
  em minutos **e** em turns.

## Riscos

Preços mudam — ficam em config com data. E `float` para dinheiro é o erro que
este card existe para não cometer.

## Objetivo de aprendizado

`Decimal` para dinheiro em Python (por que `float` quebra, `quantize`, contexto
— o paralelo do `decimal` do C#) e usage reporting dos SDKs de IA.
