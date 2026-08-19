# ADR-0021 — Prompt caching adiado: o limiar medido não é alcançado por uma conversa real

- **Status:** aceito
- **Data:** 2026-08-19
- **Substitui:** [ADR-0020](0020-prompt-caching-no-adapter-do-professor.md)
- **Evidência:** [`docs/medicao-latencia.md`](../medicao-latencia.md) §5.2 e §5.3

## Contexto

O ADR-0020 foi escrito e aceito **no mesmo dia** que este, decidindo implementar
prompt caching no adapter do professor com economia estimada de ~30–35%. Ele
assumiu, sem medir, que o **prefixo mínimo cacheável** da API era de ~1.024
tokens — o valor da família Sonnet/Opus.

A medição desmentiu a premissa central.

**Limiar medido para `claude-haiku-4-5`: 4.096 tokens.** Bisseção com
`cache_control` no bloco de `system` (§5.2 da medição):

| Prefixo | Cache engatou? |
|---|---|
| até **3.967** tok | **não** |
| a partir de **4.217** tok | **sim** |

**Por que isso invalida a decisão:** o `SYSTEM_PROMPT` do professor tem ~700
tokens e cada troca do histórico ~150. Uma conversa precisaria de **~22 trocas**
para o prefixo cruzar 4.096. Uma sessão real de 10–15 turns nunca chega lá.
Confirmado na prática: nas chamadas com o prompt real (1.084 tokens de entrada),
`cache_creation_input_tokens` e `cache_read_input_tokens` foram **0 em todas**.

O ADR-0020 decidia implementar, testar e monitorar um mecanismo que, com o
prompt atual, **nunca é acionado**. Um teste que assere `cache_read > 0` falharia
sempre; o log de `usage` mediria zero para sempre.

## Decisão

**Não implementar prompt caching agora. Manter a disciplina de prefixo estável,
que é gratuita e preserva a opção.**

1. **O CARD-007 não implementa `cache_control`** nem o teste que o ADR-0020 pedia.
2. **As regras de higiene de prefixo do ADR-0020 permanecem em vigor**, porque
   custam zero e são boa prática independentemente: ordem de renderização fixa
   (`system` → histórico → fala nova), prompt em arquivo versionado, e **proibido
   conteúdo volátil no prefixo** (timestamp, id de request, contador de turn).
   Sem elas, ativar caching depois exigiria caçar invalidadores espalhados.
3. **O `UsageEvent` (CARD-014) registra as três contagens de entrada
   separadamente** — não-cacheada, escrita e leitura. Este item do ADR-0020
   **sobrevive**: é o instrumento que detecta a mudança de regime, e sem ele não
   há como saber que o caching passou a valer a pena.
4. **Gatilho para reabrir:** o `system` prompt cruzar ~4.096 tokens por motivo
   **pedagógico** — tipicamente os exemplos few-shot que o eval (Fase 4) vier a
   justificar. Nesse cenário o caching deixa de ser otimização e vira consequência
   gratuita de uma decisão tomada por outro motivo.

### A conta que sustenta o gatilho

Acima do limiar, o ganho é grande e está medido (§5.3): a entrada fica **92% mais
barata** a partir da segunda chamada. Inflando o prefixo até 4.096 tokens:

- escrita, uma vez: 4.096 × 1,25 = 5.120 tokens-equivalentes;
- leitura, nas seguintes: 4.096 × 0,1 = 410;
- linha de base atual, sem cache: ~1.100 por chamada.

O ponto de equilíbrio é **~6 turns** na mesma conversa. Numa sessão de 15 turns a
economia é de ~35% — o número que o ADR-0020 estimou, mas **só válido se os
~3.400 tokens de recheio forem conteúdo útil**. É isso que amarra o gatilho ao
eval em vez de a um capricho.

## Alternativas consideradas

### Alternativa A — Implementar mesmo assim (manter o ADR-0020)

- **O que é:** ativar `cache_control` e esperar que ajude nas conversas longas.
- **Por que foi rejeitada:** entrega complexidade e um teste que nunca fica verde
  em troca de economia zero no caso típico. Pior: cria a ilusão de que o custo
  está otimizado, e ilusão de otimização impede a otimização real.

### Alternativa B — Inflar o system prompt agora até cruzar 4.096 tokens

- **O que é:** acrescentar ~3.400 tokens de exemplos ao prompt para forçar o
  limiar, colhendo os ~35% calculados acima.
- **Por que foi rejeitada agora:** o prompt do professor está **congelado por
  decisão do desenvolvedor** até existir o eval (Fase 4), justamente para não
  trocar qualidade pedagógica por métrica sem baseline. Inflar o prompt com
  exemplos escolhidos no escuro é exatamente essa troca — com o agravante de que
  few-shot mal escolhido **piora** a saída do modelo. O ADR-0020 já tinha
  proibido padding pelo mesmo motivo ("inflar o prompt para economizar é trocar
  custo por custo"); a medição não muda esse julgamento, só o torna tentador.
- **Continua disponível**, e vira automática quando o gatilho da decisão 4 for
  atingido.

### Alternativa C — Trocar para um modelo com limiar menor

- **O que é:** usar Sonnet, cujo mínimo cacheável é ~1.024 tokens.
- **Por que foi rejeitada:** Sonnet custa 3× a entrada e 3× a saída do Haiku
  (US$ 3/US$ 15 contra US$ 1/US$ 5 por MTok). Trocar de modelo para poder
  descontar 90% de uma parcela que ficou 3× maior é aritmética perdedora, e
  contraria o ADR-0010, que reservou Sonnet para o modo qualidade.

## Consequências

**Positivas**

- Um mecanismo que não funcionaria não entra no CARD-007 — menos código, menos
  teste falso-negativo, menos falsa sensação de custo otimizado.
- A projeção de custo volta a ser honesta: a alavanca de caching sai da conta
  (ver `analise-custo-e-precificacao.md` §9), o que **aumenta** o custo projetado
  por turn e reforça a urgência do CARD-015 (quotas).
- A disciplina de prefixo estável fica de graça e mantém a porta aberta.
- O projeto ganha um número que não estava em documentação nenhuma: **o limiar do
  Haiku 4.5 é 4.096 tokens**, medido nesta base de código.

**Negativas — o preço aceito**

- **Fica dinheiro na mesa nas conversas longas** (22+ trocas), onde o caching
  engataria sozinho. Aceito porque essas conversas são raras e o ganho absoluto
  nelas é pequeno perto da complexidade de manter o mecanismo por elas.
- **Uma regra sem verificação executável.** A proibição de conteúdo volátil no
  prefixo (decisão 2) não tem, agora, nenhum teste que a denuncie — porque o
  sinal que a denunciaria (`cache_read` = 0) é o estado normal. É disciplina
  escrita, não gate. Risco real de erodir até o gatilho ser atingido.
- **Dois ADRs no mesmo dia sobre o mesmo assunto**, sendo o segundo a correção do
  primeiro. Registrado como está: é o custo de ter escrito o ADR-0020 sobre uma
  premissa não medida, e o post-mortem correspondente é mais valioso que o
  disfarce.

**Equivalente mental .NET:** é o caso do índice que você cria confiante e o plano
de execução ignora, porque a seletividade não atinge o limiar do otimizador. O
índice não está errado — a premissa sobre quando ele seria usado é que estava. E
descobrir isso exige olhar o plano, não o código.
