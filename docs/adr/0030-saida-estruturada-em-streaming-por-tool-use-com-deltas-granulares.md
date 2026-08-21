# ADR-0030 — Saída estruturada em streaming por tool use com deltas granulares

- **Status:** aceito
- **Data:** 2026-08-21
- **Relacionado:** ADR-0022 (ordem dos campos), ADR-0021 (caching adiado),
  ADR-0009/0010 (modelo e custo), CARD-007
- **Fecha:** o risco técnico que o ADR-0022 deixou explicitamente em aberto
- **Evidência:** `backend/benchmarks/llm_streaming_spike.py` e
  `benchmarks/results/llm_streaming_spike.json`, executados em 2026-08-21

## Contexto

O ADR-0022 decidiu que `spoken_reply` é o primeiro campo da resposta do
professor e registrou, na própria decisão, o que ele **não** podia resolver:

> Ordem de chaves num JSON gerado por LLM é **aderência a prompt, não
> garantia**. […] O CARD-007 tem de verificar isso empiricamente antes de
> fechar o desenho.

O CARD-007 listou três mecanismos possíveis. Na conferência de hoje apareceu um
quarto, GA e sem beta header, que o card não conhecia porque não existia quando
ele foi escrito: `output_config={"format": {"type": "json_schema", …}}`.

Além disso, **duas premissas do card não sobreviveram à verificação**:

- *"`jiter` já está na árvore de dependências (o `pydantic-core` a usa)"* —
  **falso**. `uv run python -c "import jiter"` → `ModuleNotFoundError`. O
  `pydantic-core` embute o *crate* Rust, não o módulo Python;
- o SDK `anthropic` publicou **1.0.0** em 2026-08-20 e **não estava instalado**
  no backend (o `benchmarks/llm_haiku.py` importava uma biblioteca que o
  `pyproject.toml` não declarava).

## O que foi medido

Quatro mecanismos, prompt real (v1.md, `sha256:5903387004506a55`), fala longa
(291 chars), `claude-haiku-4-5`, 3 execuções úteis após 1 de aquecimento:

| Opção | TTFT | 1ª fala legível | `spoken_reply` 1º | Ordem estável |
|---|---|---|---|---|
| **A — tool use + `eager_input_streaming`** | 0,88 s | **0,88 s** | **3/3** | **sim** |
| B — texto livre + parser parcial | 1,01 s | 1,04 s | **2/3** | **não** |
| C — duas chamadas (só a da fala) | 0,55 s | 0,55 s | 3/3 | sim (trivial) |
| D — `output_config.format` | 1,04 s | 1,35 s | 3/3 | sim |

**A rodada 3 da opção B produziu isto:**

```
{"has_mistakes": true, "original": "So yesterday I was talki…
```

O modelo reordenou as chaves e `spoken_reply` saiu do primeiro lugar. É o risco
do ADR-0022 acontecendo, em 1 de 3 execuções, com o prompt pedindo a ordem
explicitamente. **Aderência a prompt não é garantia — agora com número.**

## Decisão

**A saída estruturada do professor é uma *tool* com schema estrito, consumida em
streaming com `eager_input_streaming: true`.**

1. **Opção A.** O schema é imposto pelo provedor (o modo estrito exige
   `required` com todas as chaves e `additionalProperties: false`), e os deltas
   já chegam como JSON parcial (`input_json_delta`).
2. **`eager_input_streaming: true` é obrigatório na definição da tool**, e não é
   beta nem header. Sem ele os deltas podem não vir na granularidade que a
   cascata precisa — e a cascata **deixaria de existir sem erro nenhum**, que é
   a mesma classe de falha silenciosa do ADR-0022.
3. **O parse incremental é o `jiter` com `partial_mode="trailing-strings"`.** É
   dependência **nova** (0.16.0), não transitiva. O modo importa: com
   `partial_mode=True` o parser devolve `{}` enquanto a aspa de fechamento não
   chegar — ou seja, a fala só apareceria inteira, que é literalmente esperar o
   objeto fechar.
4. **A validação final é feita à mão, não com pydantic.** O card sugeriu
   pydantic estrito; o ADR-0008 e a skill de arquitetura reservam pydantic para
   a borda `api/`. São seis campos de tipo conhecido e o schema já foi imposto
   pelo provedor: a fronteira anti-corrupção cabe em vinte linhas. **Divergência
   deliberada do texto do card, resolvida a favor da regra de camada.**
5. **Fora do schema é `LlmError`, nunca texto cru adiante.** O fallback do
   protótipo (`except json.JSONDecodeError` → tratar o texto cru como
   `spoken_reply`) mandava a mensagem de erro do modelo direto para o TTS.
6. **Duas zonas de retry, e elas caem de graça do desenho.** A conexão só abre
   no `__aenter__` do `async with`, que está dentro do gerador e antes do
   primeiro `yield`: todo retry do SDK (`max_retries=2` por default) acontece
   necessariamente **antes** da primeira sentença. Depois dela não existe retry
   possível — só `LlmError`. O preço é que o tempo de parede pode chegar a
   `teacher_timeout_seconds × 3`, e por isso o timeout é de **uma tentativa**.
7. **O adapter expõe as três contagens de entrada** (`input`, `cache_creation`,
   `cache_read`) no `FeedbackReady`, como o ADR-0021 item 3 exigiu. Hoje as duas
   de cache são 0 em toda chamada; é justamente por isso que precisam ser
   registradas.

### O que isso custa em tokens de entrada

O schema da tool viaja na requisição: a entrada medida subiu de **1.084 tokens**
(linha de base §5.1, sem tool) para **1.473–1.522**. São ~400 tokens a mais por
chamada, ~US$ 0,0004 no Haiku. Aceito: é o preço da garantia de schema, e é uma
ordem de grandeza menor que a alternativa C, que **dobra** a entrada.

## Alternativas consideradas

### Alternativa B — Texto livre + parser tolerante

- **O que é:** o prompt pede JSON, o adapter acumula `text_delta` e parseia
  parcialmente.
- **Por que foi rejeitada:** **reordenou as chaves em 1 de 3 execuções medidas**,
  com o prompt pedindo a ordem explicitamente. Um produto cujo alvo de latência
  depende da ordem não pode apostar em 67% de aderência. Além disso volta a
  depender de prompt para a **estrutura**, não só para a ordem: nada impede o
  modelo de inventar um campo ou omitir outro.

### Alternativa C — Duas chamadas separadas

- **O que é:** uma chamada só para a fala (0,55 s de TTFT medidos — o mais
  rápido de todos) e outra para as correções.
- **Por que foi rejeitada:** **dobra os tokens de entrada** num produto cujo
  custo é 100% LLM (o `system` e o histórico são reenviados inteiros), e cria o
  risco de as duas saídas discordarem — a correção citando uma fala que o outro
  ramo não produziu. Já rejeitada como padrão no ADR-0022, alternativa B.
  **Permanece como última saída**, agora com o ganho quantificado: 0,33 s a menos
  que a opção A.

### Alternativa D — `output_config={"format": {"type": "json_schema", …}}`

- **O que é:** saída estruturada nativa, GA, sem beta header. Os deltas chegam
  como `text_delta` com o schema imposto pelo provedor — a garantia de A com o
  caminho de B.
- **Por que foi rejeitada:** funcionou e preservou a ordem em 3/3, mas entregou a
  primeira fala legível em **1,35 s contra 0,88 s** de A — **0,47 s a mais**, num
  orçamento total de ~1,8 s. É a segunda melhor opção e a primeira candidata a
  reavaliação se A der problema.
- **Ressalva registrada:** `output_config` também carrega `effort`, que **não é
  aceito no Haiku 4.5**. São campos independentes; o spike verificou `format`
  isoladamente com `claude-haiku-4-5`, e ele funciona.

## Consequências

**Positivas**

- O risco em aberto do ADR-0022 está **fechado com medição**, não com
  argumento — e fechado a favor da decisão que já estava tomada.
- A primeira sentença sai em **0,68–0,76 s** medidos através do adapter de
  produção, contra 2,05–3,74 s da resposta inteira: a cascata recupera
  **1,3 s a 3,1 s**.
- O parser incremental e o corte por sentença custam **~0,05 s** sobre o TTFT
  (0,60–0,73 s medidos em §5.1). O código próprio é praticamente de graça.
- O schema deixa de depender de aderência a prompt: o F9 do diagnóstico continua
  morto.

**Negativas — o preço aceito**

- **~400 tokens de entrada a mais por chamada** (o schema da tool viaja junto).
  Barato hoje, e o instrumento para vigiar isso é o `UsageEvent` do CARD-014.
- **`eager_input_streaming` é uma linha que ninguém suspeitaria ser crítica.**
  Removê-la não quebra teste de conteúdo nenhum: só a latência sobe. Mesma classe
  de armadilha do ADR-0022, e mitigada do mesmo jeito — um teste assere que a
  flag está lá.
- **Duas dependências novas** (`anthropic`, `jiter`) e uma transitiva relevante
  (`httpx2`, o cliente HTTP do SDK 1.x). As três entraram nas listas `forbidden`
  de `domain` e `application` no mesmo commit.
- **O SDK 1.x tem quebras que mordem aqui e não são óbvias:**
  `temperature`/`top_p`/`top_k` removidos (`TypeError`), HTTP migrado para
  `httpx2`, `messages.parse(stream=True)` inexistente, e
  `isinstance(x, anthropic.Stream)` que **não casa** com o objeto de
  `messages.stream()`.
- **Um `# type: ignore[arg-type]` na fábrica.** O `AsyncAnthropic` real não
  satisfaz estruturalmente o `Protocol` mínimo do adapter porque `stream()` é
  uma pilha de overloads com TypedDicts do próprio SDK. A alternativa —
  reproduzir a assinatura do SDK no Protocol — é o acoplamento que o Protocol
  existe para evitar. A costura é exercitada de verdade pelo teste marcado
  `slow`, que chama a API real e passou.
- **Depender de uma flag de granularidade de streaming é depender de detalhe de
  provedor.** Se ela mudar de nome ou de semântica, a queda é para a opção D,
  que está medida e pronta.

**Equivalente mental .NET:** é a diferença entre desserializar um payload
inteiro com `JsonSerializer.Deserialize<T>` e ler com `Utf8JsonReader` sobre um
buffer que ainda está chegando — com a garantia extra de que o produtor validou
o contrato antes de emitir.
