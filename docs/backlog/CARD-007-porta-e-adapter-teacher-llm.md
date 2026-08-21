# CARD-007 — Porta TeacherLlm em streaming + parse incremental que libera `spoken_reply` frase a frase

- **ID:** CARD-007 · **Épico:** Fase 1 — Fatia vertical em cascata
- **Plataforma:** backend/IA · **Esforço:** **G — quebre se não couber numa sessão**
- **Status:** **concluído** (2026-08-21) · branch `card-007-porta-e-adapter-teacher-llm`
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

---

## Execução — 2026-08-21

### O spike, antes de qualquer código de produção

Rodado com `benchmarks/llm_streaming_spike.py`, prompt real, `claude-haiku-4-5`,
3 execuções úteis após 1 de aquecimento. **Quatro** opções, não três — a quarta
(`output_config.format`) é GA e não existia quando o card foi escrito.

```
modelo=claude-haiku-4-5  prompt=v1.md sha256:5903387004506a55
fala   sha256:924904ef26e86901 (291 chars)

A: ttft=0.88s  1a-fala=0.88s  total=3.72s  spoken_reply-primeiro=True   ordem-estavel=True
B: ttft=1.01s  1a-fala=1.04s  total=3.55s  spoken_reply-primeiro=False  ordem-estavel=False
C: ttft=0.55s  1a-fala=0.55s  total=1.65s  spoken_reply-primeiro=True   ordem-estavel=True
D: ttft=1.04s  1a-fala=1.35s  total=3.64s  spoken_reply-primeiro=True   ordem-estavel=True

custo desta execução: US$ 0.0335 (15624 tok entrada, 3571 saída)
```

**O achado.** A rodada 3 da opção B:

```
['<não parseou: \'{"has_mistakes": true, "original": "So yesterday I was talki\'>']
```

O modelo reordenou as chaves, com o prompt pedindo a ordem explicitamente. O
risco que o ADR-0022 registrou em aberto aconteceu em 1 de 3 execuções — e é a
razão de a opção B estar morta. **Escolhida a opção A**, virou
[ADR-0030](../adr/0030-saida-estruturada-em-streaming-por-tool-use-com-deltas-granulares.md).

### Três premissas do card que a verificação desmentiu

| O card afirmava | Verificado em 2026-08-21 |
|---|---|
| *"`jiter` já está na árvore de dependências (o `pydantic-core` a usa)"* | **Falso.** `ModuleNotFoundError`. O `pydantic-core` embute o *crate* Rust, não o módulo Python. É dependência nova (0.16.0) |
| SDK `anthropic` (protótipo em 0.34.0) | **1.0.0**, publicado em 2026-08-20 — e **não estava instalado** no backend: `benchmarks/llm_haiku.py` importava uma lib que o `pyproject.toml` não declarava |
| Três opções de saída estruturada | **Quatro.** `output_config={"format": …}` é GA, sem beta header, e ficou em segundo lugar na medição |

### Critérios de aceite, um a um

| Critério | Evidência |
|---|---|
| 1ª `SpokenSentence` antes de o JSON fechar | `test_primeira_sentenca_sai_antes_de_o_json_fechar` — stream que **nunca** emite `}`; o teste assere `SpokenSentence(text="Hi there, how are you today?")`. Se o adapter esperasse o objeto, não sairia nada |
| Teste falha se `spoken_reply` deixar de ser a 1ª chave | `test_teacher_prompt.py` — 6 testes, incluindo a ordem completa no prompt **e** no `input_schema` da tool |
| Resposta fora do schema → `LlmError`, sem texto cru | `test_resposta_fora_do_schema_vira_llm_error` (4 casos) + `test_resposta_sem_tool_use_vira_llm_error` |
| Sentenças já emitidas não são desditas | `test_sentencas_ja_emitidas_nao_sao_desditas_pelo_erro` |
| Geração cancelada ao abandonar a iteração | `test_abandonar_a_iteracao_fecha_o_stream` — `aclose()` → `GeneratorExit` → saída do `async with` → `__aexit__` registrado |
| Adapter sem estado entre chamadas | `test_adapter_nao_guarda_estado_entre_duas_chamadas` + `test_adapter_so_guarda_configuracao` (inspeciona `vars()`) |
| **Medição do tempo até a 1ª sentença** | §8.2 da medição: **0,76 s** (curta) e **0,68 s** (longa), medidos **através do adapter de produção**. Insumo hasheado no script |

### Gates

```
uv run ruff format --check src tests   → format OK
uv run ruff check src tests            → All checks passed!
uv run mypy                            → Success: no issues found in 54 source files
uv run lint-imports                    → Contracts: 4 kept, 0 broken.
uv run pytest --cov --cov-fail-under=80 → 122 passed, 5 deselected; total 92,78%
uv run coverage report --include="*/domain/*,*/application/*" --fail-under=90 → 100%
uv run pytest -m slow …integration     → 2 passed (chamou a API real)
```

Suíte: **80 → 122** testes. Cobertura global **91,85% → 92,78%**; núcleo em 100%.

### O gate morde — par completo, como no CARD-006

Mesma violação (`import anthropic` em `voicecoach/application/ports/__init__.py`),
duas configurações:

```
1) 'anthropic' NA lista forbidden:
   voicecoach.application is not allowed to import anthropic:
   -   voicecoach.application.ports -> anthropic (l.3)

2) mesma violação, 'anthropic' FORA da lista:
   application não conhece framework nem SDK de provider KEPT
   Contracts: 4 kept, 0 broken.
```

Entraram no `forbidden` de `domain` **e** `application`, no mesmo commit que as
instalou: `anthropic`, `jiter` e **`httpx2`** — este último porque é o cliente
HTTP real do SDK 1.x e `httpx` na lista não o cobre (lição da Q8, CARD-005).

### Item de ADR da DoD — critério citado (LEARNING-0003)

Conferido contra `docs/adr/README.md` § "Quando um ADR é OBRIGATÓRIO":

- **Critério 1 (dependência externa):** `anthropic` 1.x e `jiter` → **ADR-0030**
- **Critério 3 (custo recorrente):** o mecanismo escolhido acrescenta ~400 tokens
  de entrada por chamada; a alternativa C dobraria a entrada → **ADR-0030**
- **Critério 2 (fronteira):** a porta devolve um **fluxo de eventos**, e não o
  `TeacherFeedback` que a visão §D previa → **ADR-0031**
- **Critério 6 (contraria convenção estabelecida):** o card pedia validação com
  pydantic estrito; o ADR-0008 e a skill reservam pydantic à borda `api/`.
  Resolvido a favor da regra de camada, registrado no **ADR-0030, item 4**

### Regra do explicador — desfecho de cada pergunta

| Pergunta | Desfecho |
|---|---|
| **Q7** (`Protocol` e o momento em que um fake não satisfaz a porta) — reapresentada na abertura | **em aberto.** Não respondida nem dispensada; o desenvolvedor pediu para seguir. Continua em `docs/perguntas-em-aberto.md` |
| **Q9** (igualdade de `@dataclass`) — reapresentada na abertura | **em aberto**, mesma razão |
| **Q10** (`jiter.partial_mode=True` sobre buffer truncado), feita **antes** de escrever o parser | **errada** → demonstrada com as três chamadas no terminal → **reformulada uma vez** (quais trechos podem ir ao TTS com `trailing-strings`) → **respondida corretamente** (`Só "Hi there."`). **Fechada** |

> O desenvolvedor pediu explicitamente, no meio da sessão, que não houvesse mais
> perguntas. Q7 e Q9 **não** foram fechadas por explicação do agente
> (LEARNING-0004): seguem na fila para a abertura do CARD-008.

### Dívidas explícitas

| Dívida | Onde resolve |
|---|---|
| **Política fina de retry/backoff.** Hoje só existe o `max_retries=2` default do SDK e o timeout de uma tentativa; não há backoff próprio nem classificação de erro retentável | Card próprio, gatilho: primeira falha de provedor observada em uso real |
| **`# type: ignore[arg-type]` na fábrica.** O `AsyncAnthropic` não satisfaz estruturalmente o `Protocol` mínimo do adapter (o `stream()` do SDK é uma pilha de overloads). Coberto pelo teste `slow`, que chama a API real | Gatilho: o SDK publicar um Protocol público de `messages` |
| **O prompt ainda diz "WhatsApp" e usa markup do WhatsApp** (`~til~`, `*asterisco*`). É conteúdo **congelado** até a Fase 4 (ADR-0022), e o canal será descontinuado (ADR-0001) | Fase 4 (eval), junto com a revisão do prompt |
| **Uma linha nova no prompt**: *"The keys MUST appear in exactly the order shown above."* É instrução sobre ordem de serialização, dentro da exceção estreita do ADR-0022 — mas é uma linha a mais no prompt congelado. Registrada por honestidade | Fase 4 |
| **`config.py` não tem política de `max_history_items`.** O histórico entra inteiro pela porta; quem apara é o chamador, que ainda não existe | CARD-009 |
| **Não há adapter alternativo de LLM** (o card previa "esqueletos" como corte). Uma porta bem desenhada já permite a troca manual — Parte F da visão | Sem gatilho previsto |
