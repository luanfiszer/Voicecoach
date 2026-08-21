# Prompt — CARD-007: Porta `TeacherLlm` em streaming + parse incremental frase a frase

- **Tipo:** prompt de sessão, complemento de `/executa-card 007`
- **Escrito em:** 2026-08-21, no fechamento e merge do CARD-006 (PR #11, `fcdbe02`)
- **Status:** não executado

> **Este prompt não substitui o `/executa-card`.** Aquele comando carrega o
> protocolo (branch, ordem de leitura, premissas antes do plano, DoD item a
> item, convenção de commit). **Rode `/executa-card 007` e leia isto junto** —
> aqui está só o que é específico deste card, a arqueologia já feita, e as três
> **premissas do card que a arqueologia desmentiu**.

---

## 0. Antes do plano: a fila do explicador tem dívida que é DESTE card

`docs/perguntas-em-aberto.md` tem **6 perguntas abertas**. Duas apontam para cá,
e uma delas está marcada no próprio arquivo com o texto *"Volta no CARD-007"*.
Reapresente-as **na abertura, antes do plano**:

| # | Pergunta | Por que é deste card |
|---|---|---|
| **Q7** | O que `Protocol` faz que dispensa um framework de mock, e **em que momento** se descobre que um fake não satisfaz a porta? | **Dispensada pelo desenvolvedor no CARD-006** e explicitamente adiada para cá. Este card cria o segundo fake de porta — e o primeiro cuja assinatura devolve um **`AsyncIterator`**, onde a incompatibilidade é mais fácil de cometer e mais difícil de ver |
| **Q9** | Igualdade de `@dataclass`: por que dois objetos com um campo diferente não são iguais, e por que o Python **proíbe** usá-los como chave de dict/set? | `TeacherEvent` é união fechada de dataclasses, e o teste do stream vai **comparar listas de eventos**. É a igualdade estrutural que faz `assert eventos == [SpokenSentence("Hi there."), ...]` funcionar |

> **Precedente de processo, do CARD-006:** naquela sessão a Q3 foi perguntada
> **antes** de escrever as listas `forbidden`, a primeira resposta estava
> parcialmente errada, e **a execução desmascarou tanto a resposta quanto a
> pergunta** (a violação que se supunha vermelha passou verde). Foi reformulada
> uma vez e fechou. Esse é o padrão a repetir: pergunta com consequência
> observável, conferida rodando na hora.

A melhor pergunta desta sessão está pronta e tem resposta conferível em três
linhas de terminal: **§4.2**. Ela é candidata natural a uma das duas.

---

## 1. Por que este é o próximo card

Caminho crítico: `018 → 006 → **007** → 008 → 009 → 010 → 012`. O CARD-006 foi
mergeado em `main` (PR #11) com os gates verdes — a porta de STT, os dois
adapters e o `Transcript` existem. O 007 vem agora porque **é o único componente
do caminho cujo desenho não pode ser convertido depois**: adapter batch devolve
um objeto, adapter em streaming devolve um fluxo, e "streamar depois" é
reescrever o card inteiro.

**Esforço G — o card manda quebrar se não couber numa sessão.** Leve isso a
sério e negocie o corte no plano, não às duas da manhã.

O que este card compra, em números medidos ([medição §5.1](../medicao-latencia.md)):
TTFT de **0,60–0,73 s praticamente constante**, resposta inteira de **1,86 s
(fala curta) a 3,48 s (fala longa)**. A diferença — **1,1 s a 2,9 s** — é o que
a cascata recupera, e é a razão de existir do card.

---

## 2. O que já está decidido e não se rediscute

- [**ADR-0022**](../adr/0022-ordem-dos-campos-da-resposta-do-professor-e-contrato-de-latencia.md)
  — `spoken_reply` é o **primeiro** campo; `translation_pt` o último. A ordem é
  contrato de latência. **O item 4 do ADR manda um teste que assere isso**, e o
  próprio ADR explica por quê: o modo de falha é silencioso — reordenar não
  quebra nada, só a latência sobe.
- [**ADR-0021**](../adr/0021-prompt-caching-adiado-o-limiar-medido-nao-e-alcancado.md)
  — **sem prompt caching.** O limiar medido é 4.096 tokens (não 1.024) e a
  conversa deste produto não chega lá; seriam ~22 trocas. Mas o adapter
  **expõe as três contagens de entrada** (`input`, `cache_creation`,
  `cache_read`) para o CARD-014 — é o instrumento que detecta a mudança de
  regime. Errar caching não é perder desconto, é pagar ~25% a mais (medição §5.3).
- **ADR-0009 / ADR-0010** — o modelo do professor é `claude-haiku-4-5` (já em
  `config.teacher_model`), o gasto de API é restrito ao Claude, e há orçamento
  diário de US$ 1,00 em `daily_budget_usd`.
- **O prompt do professor está congelado** até o eval da Fase 4, **com uma
  exceção estreita**: a ordem de serialização dos campos (ADR-0022). Conteúdo,
  tom, regras pedagógicas e tamanho **não se tocam nesta sessão**.

---

## 3. Arqueologia — verificada no repositório em 2026-08-21

### 3.1 Três premissas do card que a verificação DESMENTIU

Leia esta seção antes do plano. O texto do CARD-007 foi escrito em 2026-08-19 e
três afirmações dele não sobrevivem à conferência.

| O card afirma | O que se verificou | Consequência |
|---|---|---|
| *"`jiter` **já está na árvore de dependências** (o `pydantic-core` a usa)"* | **Falso.** `uv run python -c "import jiter"` → `ModuleNotFoundError`. O `pydantic-core` embute o **crate Rust**, não o módulo Python. `jiter` é pacote PyPI separado (**0.16.0**) | É **dependência nova**. Entra no `pyproject.toml` e nas listas `forbidden` de `domain` e `application` **no mesmo commit** (ADR-0012). E dispara o **critério 1** do `docs/adr/README.md` |
| *"SDK `anthropic`"* sem versão, com o protótipo em `0.34.0` como referência | O `anthropic` publicou **1.0.0 em 2026-08-20** — ontem. É major nova | O backend nasce em 1.x. **O `english_teacher_bot/teacher.py` é código 0.x e não é modelo copiável** — ver §3.3 |
| As três opções de saída estruturada (A: tool use + `input_json_delta`; B: texto livre + parser; C: duas chamadas) | **Falta uma quarta**, que é GA, sem beta header, e combina a garantia de A com o streaming de B: **`output_config={"format": {"type": "json_schema", …}}`** | A tabela de alternativas do spike tem **quatro** linhas, não três. Ver §3.4 |

### 3.2 O estado do código, conferido

| Fato | Consequência para você |
|---|---|
| `application/ports/` tem `repositories.py` e `speech_to_text.py`. A porta nova é o terceiro arquivo | `speech_to_text.py` é o **modelo a seguir**: `Protocol`, dataclasses `frozen=True, slots=True`, docstring que explica *o que atravessa a fronteira e por quê* |
| `adapters/stt/` tem `factory.py`, `audio.py` e os dois adapters | O padrão de fábrica está pronto para copiar: resolve no boot, **imports locais à função** (para importar a fábrica não arrastar SDK nenhum), log do que foi escolhido |
| `SttProviderUnavailableError` herda de `RuntimeError`, **não** de `DomainError` — e a docstring diz por quê (ADR-0017: não é invariante de negócio, é configuração impossível) | `LlmError` tem a mesma pergunta a responder por escrito. Falha de schema do provedor **não** é invariante de domínio violada |
| `config.py` tem `anthropic_api_key` (obrigatório, sem default), `teacher_model`, `assistant_model`, `daily_budget_usd`. **Não tem timeout, `max_tokens` nem política de retry** | Campos novos entram lá. `Settings` é `frozen=True` e a validação é na construção |
| `src/voicecoach/worker/` continua **só com `__init__.py`** | Igual ao CARD-006: **não há consumidor**. Se aparecer `arq` no diff, o escopo vazou |
| **Não existe pasta `prompts/` no backend** | Você a cria. O card pede `prompts/teacher/v1.md` |
| Suíte hoje: **80 passed, 91,85% global; `domain` 100%, `application/ports` 100%** | O piso é 90% no núcleo e 80% global. Não deixe cair |
| Marker `slow` já existe e é deselecionado por default (`addopts = "-m 'not slow'"`), com `--strict-markers` | É onde mora um teste que chama a API de verdade — **e ele gasta dinheiro**, diferente do `slow` do CARD-006 |

### 3.3 O `teacher.py` do protótipo: leia, não copie

`english_teacher_bot/teacher.py` é a fonte do prompt pedagógico, e é o arquivo
mais perigoso desta sessão. Quatro coisas nele **não** podem atravessar:

1. **A ordem dos campos do `SYSTEM_PROMPT` é a ANTIGA** — `has_mistakes`
   primeiro, `spoken_reply` em quinto. Copiar o bloco cru **viola o ADR-0022 na
   primeira linha do card**, e o modo de falha é silencioso.
2. **O fallback de JSON inválido** (`except json.JSONDecodeError` → trata o texto
   cru como `spoken_reply`) é exatamente o que o card proíbe: falha de schema é
   `LlmError`, **nunca** texto cru adiante.
3. **Estado global de módulo** (`_history`, `_last_reply`, `_client`) — o adapter
   novo não tem estado, o histórico **entra pela porta** (mata F5/F7), e um
   critério de aceite exige que isso seja inspecionável por teste.
4. **API 0.x**: `client.messages.create(...)` síncrono, `response.content[0].text`.
   No 1.x o que muda e morde aqui: `temperature`/`top_p`/`top_k` **removidos**
   (400 se enviados), o HTTP migrou para `httpx2`, `messages.parse(stream=True)`
   **não existe mais** (use `client.messages.stream(..., output_format=Model)`),
   e `isinstance(x, anthropic.Stream)` **não casa** com o objeto de
   `messages.stream()` (é `anthropic.lib.streaming.AsyncMessageStream`).

O que **deve** atravessar: o conteúdo pedagógico do prompt, reordenado conforme
o ADR-0022 — e nada mais.

### 3.4 A quarta opção do spike

O card avalia três mecanismos. Existe um quarto, GA e sem beta header:

```python
output_config={"format": {"type": "json_schema", "schema": {...}}}
```

Com ele a resposta vem como **bloco de texto com JSON garantido pelo schema** —
ou seja, os deltas chegam como `text_delta` (o caminho da opção B) **com** a
imposição de schema do provedor (a garantia da opção A). Se a ordem das chaves
se preservar aí, é a melhor das duas.

Duas cautelas concretas, e ambas são para o spike responder, não para presumir:

- **`output_config` também carrega `effort`, e `effort` não é aceito no
  Haiku 4.5.** São campos independentes; não conclua que `format` falha porque
  `effort` falha. Verifique `format` com `claude-haiku-4-5` explicitamente.
- **Se ficar na opção A (tool use)**, os deltas granulares de JSON exigem
  `eager_input_streaming: true` **na definição da tool** — com o
  `client.messages.stream()` normal, não é beta e não é header. Sem isso, o
  `input_json_delta` pode não chegar na granularidade que a cascata precisa, e o
  spike mediria a coisa errada.

**O spike continua sendo o primeiro item do card**, agora com quatro linhas na
tabela. Ele mede duas coisas com o prompt real, e o resultado vai para o card
**antes** de qualquer código de produção: (1) a ordem das chaves no stream;
(2) se o primeiro delta de `spoken_reply` chega dentro de ~0,8 s.

---

## 4. As armadilhas — o que o texto do card não antecipa

### 4.1 Gerador assíncrono: nada roda até alguém iterar, e abandonar é cancelar

`async def` + `yield` produz um **gerador assíncrono**; o consumidor puxa com
`async for`. O equivalente mental é `IAsyncEnumerable<T>` com `yield return` — e
a diferença que importa aqui é o fim da história, não o começo:

- **Nada executa até a primeira iteração.** Um teste que chama
  `respond_streaming(...)` e não itera **não exercita nada** e passa verde.
- **Abandonar o `async for` no meio é o que cancela a geração** — e só cancela
  se o gerador for fechado. O `async with client.messages.stream(...)` fica
  *dentro* do seu gerador; quando o consumidor sai do laço, o Python chama
  `aclose()`, que levanta `GeneratorExit` no ponto do `yield`, que sai do `async
  with`, que fecha a conexão HTTP. Se você engolir essa exceção — ou guardar o
  stream fora do `async with` — a geração continua correndo e **você paga por
  tokens que ninguém vai ouvir**.
- Em C# isso seria um `CancellationToken` que você tem de passar adiante. Em
  Python o cancelamento vem de graça pelo protocolo do gerador, **desde que você
  não o desligue sem querer**.

Um critério de aceite do card depende exatamente disso: *"a geração é cancelada
— a iteração é abandonada, não deixada correndo"*. Prove com teste, não com
comentário.

### 4.2 `jiter` e o `partial_mode`: a melhor pergunta do explicador desta sessão

Três chamadas, três comportamentos diferentes sobre **o mesmo** JSON truncado —
e a escolha entre elas é a diferença entre a cascata funcionar e não funcionar.
Verificado hoje, com `jiter` 0.16.0:

```python
buf = b'{"spoken_reply": "Hi there, how ar'

jiter.from_json(buf, partial_mode="trailing-strings")
# -> {'spoken_reply': 'Hi there, how ar'}     a string incompleta VEM

jiter.from_json(buf, partial_mode=True)
# -> {}                                        a chave incompleta é DESCARTADA

jiter.from_json(buf)
# -> ValueError: EOF while parsing a string at line 1 column 23
```

**Pergunte antes de escrever o parser**, e no formato de consequência: *"o que
`partial_mode=True` devolve para este buffer, e por que isso mataria a cascata?"*
A resposta se confere colando as três linhas no `uv run python`. Errar aqui não
levanta exceção — só faz a primeira sentença nunca sair antes do objeto fechar,
que é o card inteiro falhando em silêncio.

### 4.3 O corte por sentença tem dois modos de falha opostos

- **Cortar cedo demais:** `[.!?]` seguido de espaço pega `"Mr. Smith"`,
  `"3.5 hours"`, `"i.e."`. Uma sentença partida no meio vira dois arquivos de
  áudio com prosódia errada.
- **Cortar tarde demais:** emitir a última sentença do buffer antes de ter certeza
  de que ela acabou. Com `trailing-strings`, o fim do buffer é **sempre** texto
  possivelmente incompleto — só se emite o que tem delimitador **e** mais texto
  depois dele.

O card já define a política: a **primeira** sentença sai o quanto antes (é ela
que define o ~1,8 s); as seguintes podem ser agrupadas até ~200 caracteres,
porque o TTS tem custo linear (RTF ~0,10, medição §4.2) e trecho maior significa
menos eventos.

### 4.4 Retry depois da primeira sentença é proibido

O card diz "timeout explícito e retries limitados (F8)" e, na linha seguinte,
que **retry depois de já ter emitido sentença é proibido** — o aluno ouviria a
resposta recomeçar. Na prática isso quer dizer que o adapter tem **duas zonas**:
antes do primeiro `yield` (onde retry é legítimo) e depois dele (onde só existe
`LlmError`). Torne isso explícito no código, não implícito no fluxo.

E o SDK tem `max_retries=2` por default — que **se soma** ao seu. Timeout total
de parede pode chegar a `timeout × (max_retries + 1)`.

### 4.5 Não implemente o consumidor

Este card **não** orquestra pipeline (CARD-009), **não** chama TTS nem storage
(CARD-008), **não** persiste `corrections[]` tipadas (CARD-013), **não** faz eval
(Fase 4) e **não** liga caching (ADR-0021). O adapter devolve um fluxo de eventos
e acaba aí.

### 4.6 A medição é entregável, não subproduto

*"Medição registrada no card: tempo até a primeira sentença, com o prompt real.
É o número que este card existe para produzir."* Compare-o com o TTFT medido
(0,60–0,73 s) — o delta entre os dois é o custo do seu parser, e é a única
maneira de saber se o corte por sentença está pagando por si.

Cuidado com a assimetria de insumo que mordeu o CARD-006: os arquivos de
`benchmarks/inputs/` **mudaram** desde a sessão de medição e as tabelas §3.2/§3.3
já não reproduzem byte a byte (ressalva na §3.5). Se a sua medição depender de
insumo, **versione o insumo ou registre o hash**.

---

## 5. Escopo — o que corta se estourar

Regra de desempate da reconstrução: **cede escopo, nunca latência**. O card é
**G** e manda quebrar se não couber.

- **Não corte:** o spike, a porta em streaming, o parse incremental, o corte por
  sentença, o teste da ordem das chaves (ADR-0022 item 4), o fake de
  `application`.
- **Pode virar card próprio:** a política fina de retry/backoff; a exposição das
  três contagens de uso (se o CARD-014 ainda estiver longe); o prompt versionado
  com mais de uma versão.
- **Se o spike derrubar a opção escolhida**, a queda para B ou C **é** o trabalho
  da sessão e vira nota no ADR-0022 — não é fracasso, é o card fazendo o que
  existe para fazer.

---

## 6. Governança

1. **Item de ADR da DoD — este card quase certamente gera ADR** (verifique contra
   a lista de `docs/adr/README.md` e **cite o critério**, LEARNING-0003):
   - **Critério 1 (dependência externa):** entram `anthropic` **e** `jiter`. Duas
     bibliotecas novas, uma delas descoberta contra a afirmação do card.
   - **Critério 2 (fronteira):** o que atravessa a porta é um **fluxo de eventos**,
     não um objeto — é o mesmo tipo de decisão que gerou o ADR-0029 no CARD-006.
   - **Critério 3 (custo recorrente):** o mecanismo de saída estruturada muda a
     contagem de tokens de entrada (a opção C dobra).
   - O resultado do spike — **qual dos quatro mecanismos venceu e por qual
     medição** — é conteúdo de ADR, não de seção de execução de card. Card é
     registro de trabalho; ADR é registro de decisão.
2. **Skill `voicecoach-arquitetura` desatualizada:** ela reflete os ADRs até 0023
   e **não** cobre 0024–0029. Se ela contradisser um ADR, **o ADR ganha** e a
   skill se corrige na mesma sessão. Nunca afrouxe em silêncio.
3. **Precedente dos CARDs 018 e 006:** decisão que os ADRs não cobrem vai ao
   desenvolvedor **antes da primeira linha de código**. Foi assim que nasceram o
   ADR-0028 e o ADR-0029. Pare e pergunte; não decida e documente depois.

---

## 7. Definition of Done específica deste card

Além da DoD do `CLAUDE.md`:

- [ ] **Spike executado e registrado no card antes do código de produção**, com
      as **quatro** opções na tabela e a saída de comando colada: ordem das
      chaves no stream + tempo até o primeiro delta de `spoken_reply`.
- [ ] Teste com **stream sintético que nunca fecha o objeto JSON** provando que a
      primeira `SpokenSentence` sai antes do fim — é o critério que define o card.
- [ ] Teste que **falha se `spoken_reply` deixar de ser a primeira chave**
      (ADR-0022 item 4). Sem ele o ADR erode sozinho.
- [ ] Teste que prova que **abandonar a iteração fecha o stream** (§4.1).
- [ ] Teste que prova que o adapter **não guarda estado entre duas chamadas**.
- [ ] `LlmError` com a mesma justificativa por escrito que `SttProviderUnavailableError`
      tem: por que herda do que herda, e por que **não** é `DomainError` (ADR-0017).
- [ ] `uv run lint-imports` verde, com **`anthropic` e `jiter`** nas listas
      `forbidden` de `domain` e `application` **no mesmo commit** que os instala.
      Se os contratos não morderem sozinhos, prove que mordem injetando a
      violação e revertendo — como no CARD-006.
- [ ] Cobertura: núcleo (`domain` + `application`) ≥ 90%, global ≥ 80%. **Está em
      100% / 91,85% hoje.**
- [ ] Teste de `application` usa **fake em memória**, sem tocar no SDK — e é ele
      que fecha a Q7.
- [ ] **Medição do tempo até a primeira sentença** registrada no card, com insumo
      versionado ou hash anotado.
- [ ] Q7 e Q9 reapresentadas na abertura, com desfecho registrado no card:
      respondida / dispensada pelo dev / em aberto. **Item fechado pelo agente com
      a própria explicação não conta** (LEARNING-0004).
- [ ] Card atualizado e tabela de `docs/backlog/README.md` atualizada.

---

## 8. Restrições

- **Branch própria** a partir de `main` (que já contém o CARD-006, `fcdbe02`).
  `main` é protegida.
- Commit **nunca** leva trailer `Co-Authored-By`
  ([LEARNING-0001](../learnings/0001-commit-com-coautoria-indesejada-do-agente.md)).
- **Não pushe nem abra PR sem perguntar.**
- **Este card gasta dinheiro de verdade** — é o primeiro que chama API paga. O
  ADR-0010 dá o teto: `daily_budget_usd` = US$ 1,00. O spike e a medição são
  poucos tokens de Haiku, mas **conte-os e registre o custo no card**. Teste que
  chama a API vive atrás do marker `slow`, nunca na suíte default.
- **Não antecipe o V2** (ADR-0003): nada de realtime, nada de STT incremental.
- **Não mexa no conteúdo do prompt do professor.** Congelado até a Fase 4, com a
  única exceção da ordem dos campos (ADR-0022).
- Responda em português. O desenvolvedor é sênior em C#/.NET e **iniciante em
  Python**: ao citar biblioteca, diga qual, por que ela e não a alternativa, e o
  equivalente mental em .NET. Idioma sem paralelo em C# — **gerador assíncrono,
  `aclose()`/`GeneratorExit`, união fechada por `match`** — pare e explique em
  3 linhas. Sem aula de injeção de dependência, repositório ou camadas.
