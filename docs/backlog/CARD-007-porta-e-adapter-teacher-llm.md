# CARD-007 — Porta TeacherLlm em streaming + parse incremental que libera `spoken_reply` frase a frase

- **ID:** CARD-007 · **Épico:** Fase 1 — Fatia vertical em cascata
- **Plataforma:** backend/IA · **Esforço:** **G — quebre se não couber numa sessão**
- **Status:** backlog
- **Dependências:** CARD-002 (config), CARD-006 (padrão de porta), ADR-0022

## Contexto

Este é o card que decide se o produto tem 1,8 s ou 3,7 s de primeiro áudio.

Medido ([medição §5.1](../medicao-latencia.md)): o **TTFT é 0,60–0,73 s e
praticamente constante**; a geração roda a **~130 tok/s**; a resposta inteira
leva 1,86 s (fala curta) a 3,48 s (fala longa). Toda a diferença entre TTFT e
total — **1,1 s a 2,9 s** — é tempo que a cascata recupera.

O [ADR-0022](../adr/0022-ordem-dos-campos-da-resposta-do-professor-e-contrato-de-latencia.md)
já pagou o pré-requisito: `spoken_reply` é o **primeiro** campo do JSON.

## Por que agora

É o gargalo do caminho crítico e o único componente cujo desenho **não pode ser
convertido depois**. Adapter batch e adapter em streaming têm forma diferente:
um devolve `TeacherFeedback`, o outro devolve um fluxo. Construir batch agora e
"streamar depois" é reescrever este card inteiro — a diferença entre construir
para streaming e converter para streaming.

## Problema

Extrair um campo de um JSON **que ainda está sendo gerado**. `json.loads` sobre
texto truncado levanta exceção; esperar o objeto fechar é exatamente o que se
quer evitar.

E um risco que o ADR-0022 deixou explicitamente aberto: **ordem de chaves em
JSON gerado por LLM é aderência a prompt, não garantia.** Dependendo de como a
saída estruturada for implementada, o provedor pode não preservar a ordem no
streaming. **Este card verifica isso empiricamente antes de fechar o desenho.**

## Proposta técnica

### A porta

```
respond_streaming(history) -> AsyncIterator[TeacherEvent]
```

`TeacherEvent` é união fechada: `SpokenSentence(text)` (n vezes) →
`FeedbackReady(TeacherFeedback)` → fim. O consumidor (CARD-009) reage a cada
evento; a porta **não** conhece TTS, storage nem fila.

`AsyncIterator` é o idioma Python sem paralelo direto em C#: uma função `async
def` com `yield` vira um gerador assíncrono, e o `async for` do consumidor puxa
item a item. O equivalente mental é `IAsyncEnumerable<T>` com `yield return` —
inclusive na parte que mais engana: **nada executa até alguém iterar**, e
abandonar a iteração no meio é o que cancela a geração.

### As três opções avaliadas — e a decisão

| Opção | Como | Por que sim / não |
|---|---|---|
| **A — Tool use com `input_json_delta`** | saída estruturada via *tool*; o SDK emite deltas de JSON parcial | **Escolhida.** O schema é imposto pelo provedor (o F9 do diagnóstico continua morto) e os deltas já vêm como JSON parcial. Custo: a ordem das chaves fica a cargo do provedor — é exatamente o risco do ADR-0022, e é o que o spike do item 1 mede |
| **B — Texto livre + parser tolerante** | prompt pede JSON; acumula `text_delta` e parseia parcial | Recuo se A não preservar a ordem. Mais controle sobre a ordem (o modelo escreve na sequência pedida), menos garantia de schema — volta a depender de aderência a prompt para a **estrutura**, não só para a ordem |
| **C — Duas chamadas separadas** | uma só para a fala, outra para as correções | Corta ainda mais o caminho crítico, mas **dobra os tokens de entrada** num produto cujo custo é 100% LLM (alavanca §9 da análise de custo), e cria risco de as duas saídas discordarem. Já rejeitada como padrão no ADR-0022, alternativa B; permanece como última saída |

**O card começa por um spike de 30 minutos** que roda A com o prompt real e
verifica: (1) a ordem das chaves no stream; (2) se o primeiro delta de
`spoken_reply` chega dentro do orçamento (~0,8 s). O resultado é registrado no
card **antes** de qualquer código de produção. Se A falhar, cai para B; se B
falhar, C — e cada queda vira nota no ADR-0022, que já previu esta bifurcação.

### Parse parcial

- `jiter` (`jiter.from_json(buf, partial_mode="trailing-strings")`) — parser de
  JSON em Rust que aceita entrada truncada e devolve o que já dá para ler,
  inclusive **string incompleta**. É a peça certa por dois motivos: já está na
  árvore de dependências (o `pydantic-core` a usa), e é a única das opções que
  não exige "consertar" o JSON antes de ler. Alternativas descartadas:
  `json-repair` (heurística de conserto — adivinha demais para um caminho
  crítico) e acumular até fechar (que é não fazer cascata).
- **Corte por sentença:** regex sobre `[.!?]` seguido de espaço, com tamanho
  mínimo para não emitir "Hi." sozinho. A **primeira** sentença sai o quanto
  antes (é ela que define o ~1,8 s); as seguintes podem ser agrupadas até
  ~200 caracteres, porque o TTS tem custo linear (RTF ~0,10 constante — medição
  §4.2) e trecho maior significa menos objetos e menos eventos.
- Validação final continua sendo `TeacherFeedback` em pydantic estrito: falha de
  schema é `LlmError`, **nunca** texto cru adiante.

### O resto

- Prompt versionado em arquivo (`prompts/teacher/v1.md`), com a ordem de campos
  do ADR-0022 e **teste que assere que `spoken_reply` é a primeira chave** —
  sem ele o ADR-0022 erode sozinho e ninguém percebe (a falha é silenciosa: só
  a latência sobe).
- Histórico **entra** pela porta (o adapter não tem estado — mata F5/F7).
- Timeout explícito e retries limitados (F8). **Retry depois de já ter emitido
  sentença é proibido** — o aluno ouviria a resposta recomeçar.
- **Sem prompt caching** ([ADR-0021](../adr/0021-prompt-caching-adiado-o-limiar-medido-nao-e-alcancado.md)):
  o limiar medido é 4.096 tokens e uma conversa deste produto não chega lá.
  Mas o adapter **expõe as três contagens de entrada** (`input`,
  `cache_creation`, `cache_read`) para o CARD-014 registrar — é o instrumento
  que detecta a mudança de regime.

## Escopo

- **In:** porta em streaming, adapter Anthropic, parse incremental, corte por
  sentença, prompt versionado, testes.
- **Out:** TTS e storage (CARD-008); orquestração (CARD-009); `corrections[]`
  tipadas (CARD-013); eval (Fase 4); caching (ADR-0021).

## Critérios de aceite

- **Dado** um stream gravado do provedor, **quando** o adapter consome,
  **então** a primeira `SpokenSentence` é emitida **antes** de o JSON fechar
  (teste com stream sintético que nunca fecha o objeto).
- **Dado** o prompt em arquivo, **então** um teste falha se `spoken_reply`
  deixar de ser a primeira chave (ADR-0022, item 4).
- **Dado** uma resposta fora do schema, **então** `LlmError` — e nenhuma
  sentença já emitida é "desdita" (o contrato do caminho triste é do CARD-009).
- **Dado** um stream com timeout, **então** falha no prazo com erro tipado e a
  geração é cancelada (a iteração é abandonada, não deixada correndo).
- **Dado** o adapter, **então** ele não guarda estado entre duas chamadas
  (inspecionável por teste).
- **Medição registrada no card:** tempo até a primeira sentença, com o prompt
  real. É o número que este card existe para produzir.

## Riscos

- **A ordem das chaves não se preservar** — mitigado pelo spike inicial e pelas
  saídas B e C, todas já registradas no ADR-0022.
- **Sentença longa demais na primeira posição** (o professor abre com uma frase
  de 40 palavras) — o alvo de 1,8 s escorrega e nada quebra. Medir, e se
  acontecer, é assunto de prompt (zona congelada, Fase 4), não de código.
- Card grande. Se não couber, o corte é o adapter OpenAI/esqueletos — **nunca**
  o streaming, que é o motivo de o card existir.

## Objetivo de aprendizado

Geradores assíncronos (`async def` + `yield`, `async for`) e o que significa
"nada roda até alguém iterar" — o `IAsyncEnumerable` do C# com a diferença de
cancelamento; e pydantic como fronteira anti-corrupção para saída de LLM.
