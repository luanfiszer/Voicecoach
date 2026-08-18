# ADR-0009 — Estratégia de modelos de IA: modelo forte para pedagogia, modelo barato para auxiliares, sempre por configuração

- **Status:** aceito
- **Data:** 2026-08-17

## Contexto

O protótipo fixa `claude-sonnet-4-20250514` (maio/2025 — ~15 meses defasado;
diagnóstico 3.k) e usa o mesmo modelo para tudo. O custo por interação
(~$0.023–0.028 na parte de IA) é dominado pelo LLM+TTS, e o produto terá
tarefas de naturezas diferentes: resposta pedagógica (qualidade manda),
classificação de tipo de erro, detecção de idioma, estimativa CEFR
(latência/custo mandam). Preços vigentes (tabela Anthropic, cache 2026-06):
Sonnet 4.6 e Sonnet 5 a $3/$15 por MTok (Sonnet 5 com intro $2/$10 até
2026-08-31); Haiku 4.5 a $1/$5.

## Decisão

1. **Dois papéis de modelo, não um modelo**: `TEACHER_MODEL` (resposta
   pedagógica — qualidade primeiro) e `ASSISTANT_MODEL` (tarefas auxiliares:
   classificação de erro, detecção de idioma, CEFR — custo/latência primeiro).
2. Valores iniciais: `TEACHER_MODEL=claude-sonnet-4-6`,
   `ASSISTANT_MODEL=claude-haiku-4-5` (Haiku a 1/3 do custo para tarefas que
   não pedem o modelo forte).
3. **Modelo é configuração revisável** (pydantic-settings), nunca literal em
   código; a revisão é trimestral ou a cada release relevante da Anthropic —
   e **qualquer troca de modelo do professor exige rodar o eval harness (P5)
   antes de promover**. Sem baseline, troca de modelo é chute tanto quanto
   troca de prompt.
4. SDK `anthropic` atualizado para versão corrente no novo backend (o 0.34.0
   do protótipo é ~2 anos defasado).

## Alternativas consideradas

### Alternativa A — Um único modelo forte para tudo
- O que é: simplicidade máxima, Sonnet em toda chamada.
- Por que foi rejeitada: paga preço de modelo forte em tarefas mecânicas
  (classificar tipo de erro não precisa dele) e acopla latência das tarefas
  auxiliares à do modelo grande. A separação por papel custa uma variável de
  config e compra a arquitetura de custo.

### Alternativa B — Um único modelo barato para tudo (Haiku)
- O que é: custo mínimo.
- Por que foi rejeitada: a resposta pedagógica é o produto — degradá-la para
  economizar centavos por interação inverte a prioridade declarada
  (qualidade de engenharia e de produto antes de custo). Hipótese a testar
  com o eval (P5): se Haiku empatar no baseline pedagógico, esta decisão é
  revisitada com dados.

### Alternativa C — Fixar o modelo mais novo disponível (Sonnet 5, preço intro)
- O que é: adotar o lançamento mais recente com desconto até 2026-08-31.
- Por que foi rejeitada como default: o preço intro expira em 2 semanas
  (volta a $3/$15 — igual ao Sonnet 4.6) e não há baseline de eval para
  comparar comportamento pedagógico entre gerações. Sem eval, escolhe-se o
  estável; com eval (P5), a promoção para Sonnet 5 é um experimento barato e
  reversível. Não é rejeição do modelo — é rejeição de trocar sem medir.

### Alternativa D — Multi-provider com fallback automático
- Já cortada na visão §F (anti-overengineering): a porta `TeacherLlm` permite
  troca manual; failover automático só com SLA que o exija.

## Consequências

**Positivas**: custo por interação cai nas tarefas auxiliares (~3× mais
baratas); latência menor onde não importa qualidade máxima; troca de modelo
vira operação de config + eval, não deploy de código; defasagem de 15 meses
eliminada.

**Negativas — o preço aceito**: duas variáveis de modelo para operar e
raciocinar; a regra "eval antes de promover" cria dependência do P5 (correta
— é a ordem que o harness já impõe); revisão trimestral é disciplina manual.

**Equivalente mental .NET:** feature policy por `IOptions` — o "qual provider
de qual serviço" mora em configuração tipada, e a promoção passa por um
gate de regressão, como um pacote só sobe com a suíte verde.
