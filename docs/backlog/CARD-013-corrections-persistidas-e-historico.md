# CARD-013 — Corrections tipadas persistidas + histórico do LLM vindo do banco

- **ID:** CARD-013 · **Épico:** Fase 2 — Domínio pedagógico
- **Plataforma:** backend · **Esforço:** M · **Status:** ✅ concluído (2026-08-26)
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


---

## Execução — 2026-08-26

Branch `card-013-corrections-persistidas`. ADRs produzidos:
[ADR-0049](../adr/0049-correction-e-entidade-persistida-e-os-campos-texto-viram-derivacao.md)
e [ADR-0050](../adr/0050-o-feedback-volta-na-retomada-e-o-buraco-do-adr-0041-fecha.md).
Postmortem sobre a regra do explicador:
[LEARNING-0005](../learnings/0005-a-fila-de-perguntas-nao-fecha-e-a-metade-nova-da-regra-ja-funciona.md).

### As três decisões levadas ao desenvolvedor antes da primeira linha de código

| Decisão | Escolha |
|---|---|
| Valores de `severity` (§4.4 do prompt) | `minor` / `moderate` / `major` |
| Quem preenche os campos velhos com 2 correções (§4.2) | **derivados da primeira**, por `legacy_summary` no domínio |
| Em que momento as correções são gravadas (§4.5) | junto do `attach_reply`, na escrita que já existia |

E a pendência de topo, cobrada na abertura: **reescrever a regra do explicador**
(LEARNING-0005), o que fecha uma decisão adiada em cinco aberturas seguidas.

### A armadilha que o prompt do card não antecipava

§4.3 mandava emitir `feedback` na retomada, mas **os quatro campos do
`FeedbackPayload` não são persistidos por este card** — só `corrections[]` é.
Reconstituir o evento do banco exigia responder de onde saem `original`,
`corrected` e `tip`, e a saída óbvia (quatro colunas novas) é dado duplicado.

A solução resolveu as duas armadilhas de uma vez: **os campos velhos viram
derivação** (`legacy_summary`, no domínio, ADR-0028), o prompt v2 **para de
gerá-los**, e isso devolve tokens — que é o que compensou o custo de latência que
a §4.1 previa. Ver ADR-0049.

### Critérios de aceite, com evidência real

**1. "2 correções ⇒ 2 Corrections persistidas, com enum válido."** ✅ Provado
duas vezes.

Contra Postgres real (ADR-0018), `tests/adapters/test_persistence.py`:
`test_duas_correcoes_persistem_ligadas_ao_turn`,
`test_o_enum_e_gravado_com_o_valor_do_membro_nao_com_o_nome` (SQL crua devolve
`("word_order","moderate")`, não `WORD_ORDER`) e
`test_o_delete_do_turn_leva_as_correcoes_junto`.

E **ponta a ponta, com o pipeline inteiro rodando** — áudio sintetizado com um
erro de propósito, `POST` real, STT, LLM `claude-haiku-4-5`, TTS, MinIO,
Postgres:

```
$ curl -s localhost:8000/v1/turns/784c57d0-.../ | jq .corrections
transcript: "Yesterday I go to store and buy 2 book."
[ {"index":0,"type":"grammar","original_excerpt":"Yesterday I go",
   "corrected_form":"Yesterday I went","severity":"major"},
  {"index":1,"type":"grammar","original_excerpt":"buy 2 book",
   "corrected_form":"bought 2 books","severity":"moderate"} ]

$ psql -c "SELECT index,type,severity FROM turn_corrections WHERE turn_id='784c...'"
 index |  type   | severity
     0 | grammar | major
     1 | grammar | moderate
```

**2. "12 turns e janela de 10 ⇒ exatamente os 10 últimos."** ✅ **Já entregue no
CARD-009**, marcado citando o teste em vez de escrever outro (§3.2 do prompt):
`test_list_by_session_corta_os_mais_velhos_e_nao_os_mais_novos` e
`test_list_by_session_devolve_so_os_concluidos_em_ordem_cronologica`
(Postgres real), mais `test_o_historico_da_sessao_chega_ao_professor`. **Nada foi
reescrito.**

**3. "Os tipos gerados mudam e o app compila."** ✅ `openapi.json` e
`packages/api-client/src/schema.d.ts` regenerados (+188 linhas); `tsc --noEmit`
verde em `@voicecoach/api-client` **e** em `@voicecoach/mobile`, **sem nenhuma
mudança no app** — que é a prova operacional de que a evolução foi aditiva.

**4. Contrato aditivo verificado.** ✅ Os quatro campos velhos continuam no
`GET` e no evento, e **está escrito quem os preenche**: `corrections[0]`, por
`legacy_summary`, com teste
(`test_com_duas_correcoes_os_campos_legados_saem_da_primeira`) e com o
contraponto da alternativa recusada
(`test_a_severidade_nao_reordena_o_que_vai_para_os_campos_legados`).

**5. `feedback` volta na retomada, teste antigo invertido, ADR-0041
atualizado.** ✅ `test_o_historico_nao_reconstroi_feedback` ficou vermelho — o
gate funcionando, não regressão — e virou
`test_o_historico_reconstroi_feedback_agora_que_a_correcao_e_persistida`, com dois
irmãos (turn sem correção; turn sem `replied_at`). Provado ponta a ponta:

```
$ curl -N -H "Last-Event-ID: chunk:1" localhost:8000/v1/turns/784c.../events
id: feedback
event: feedback
data: {"has_mistakes":true,"original":"Yesterday I go","corrected":"Yesterday I went",
       "tip":"...","corrections":[{...},{...}]}
```

O ADR-0041 teve o item 5 e a consequência negativa correspondente marcados como
completados, com o texto original preservado em citação.

**6. Latência remedida.** ✅ [medicao-latencia.md §12](../medicao-latencia.md).
Mesmo protocolo da §11 (N=10, mesmo WAV, mesmo Simulador):

| | CARD-012 | CARD-013 |
|---|---|---|
| **p50 até o primeiro áudio audível** | 2,47 s | **2,34 s** (−130 ms) |
| 1ª sentença falável do LLM (6 casos fixos) | 0,771 s | **0,845 s** (+74 ms) |

**A previsão da §4.1 estava certa sobre o mecanismo e errada sobre o saldo.** O
professor ficou 74 ms mais lento para começar a falar; o pipeline ficou 130 ms
mais rápido, porque o v2 gera **133 tokens a menos** (o array custa, mas parar de
pedir os quatro campos texto devolve mais do que ele custa) e `corrections` é o
último campo. **O número que piorou está escrito**, não arredondado.

**7. v1 e v2 comparados com casos fixos.** ✅
`benchmarks/llm_prompt_v1_vs_v2.py`, seis casos, os dois braços com o schema de
tool que é o seu; bruto em `benchmarks/results/llm_prompt_v1_vs_v2.json`.

| | v1 | v2 |
|---|---|---|
| tokens de saída (6 casos) | 1.558 | **1.425** |
| tokens de entrada (6 casos) | 7.451 | **8.927** |
| 1ª sentença falável (média) | 0,771 s | **0,845 s** |

**Uma regressão pedagógica real foi encontrada e corrigida.** No caso "ordem das
palavras" (*"Always I go to the gym before the work"*) o v2 pegou
`before the work` (preposition/minor) e **deixou passar** o erro principal. Foi
acrescentada uma regra de prioridade ao prompt (tempo verbal, concordância e
ordem das palavras superam artigo e preposição) e o caso foi rerodado: **3/3
execuções** passaram a pôr `word_order` primeiro.

Qualidade, no geral: o v2 é mais preciso (`original_excerpt` é o menor trecho
verbatim, em vez da frase inteira com `~til~` e `*asterisco*`) e menos
conservador em 2 dos 6 casos (2 correções onde o v1 dava 1) — o que é consequência
direta do teto de 2 e da tipagem, e fica registrado como observação sem eval.

### Quality gates

```
uv run ruff format --check src tests   109 files already formatted
uv run ruff check src tests            All checks passed!
uv run mypy                            Success: no issues found in 107 source files
uv run lint-imports                    Contracts: 4 kept, 0 broken.
uv run pytest --cov --cov-fail-under=80   305 passed · total 92,72%
                                          domain 100% · application 96–100%
```

**O gate morde?** Sim, e foi demonstrado duas vezes nesta sessão, de propósito:
o `mypy` com `Found 17 errors in 5 files` quando `TeacherFeedback` mudou de
forma, e o `InvalidRequestError` do `lazy="raise_on_sql"` com o `selectinload`
omitido. Nenhuma violação de import foi injetada porque nenhuma dependência
nova entrou — não há lista `forbidden` a atualizar neste card.

### Item de ADR, contra critério escrito (LEARNING-0003)

Consultada a lista "Quando um ADR é OBRIGATÓRIO" de `docs/adr/README.md`:

- **ADR-0049** — critério **2** (fronteira: formato de dados persistidos +
  contrato de API) e critério **5** (difícil de reverter: renomear membro de enum
  invalida linha gravada **e** quebra cliente).
- **ADR-0050** — critério **2** (altera o que a retomada entrega, que é contrato
  sob a política aditiva do ADR-0008).
- **Critério 3 (custo recorrente)** foi avaliado e **não** gerou ADR próprio: o
  aumento de ~5% por chamada está registrado como consequência negativa do
  ADR-0049, com o gatilho (prompt caching, ADR-0021) já escrito lá. Decisão nova
  não houve — o teto do ADR-0010 não mudou.

### Regra do explicador — desfecho de cada pergunta

Duas perguntas, as duas **no ponto da decisão**, antes do código, sobre
consequência observável, conferidas rodando na hora:

| # | Pergunta | Desfecho |
|---|---|---|
| P1 | Campo novo no `TeacherFeedback` **com default**: o que os gates dizem? | **"não sei"** → demonstradas as duas variantes (com default: `mypy Success` + `28 passed`; obrigatório: `17 errors`), **reformulada uma vez** para `tuple` vs. `list` → 2ª resposta **errada**. Não fechou: vira **Q15** em `perguntas-em-aberto.md` |
| P2 | Esquecer o `selectinload` do relacionamento novo: erro em runtime, N+1 silencioso ou lista vazia? | **respondida corretamente na primeira**, e conferida injetando a omissão: `InvalidRequestError: 'TurnRow.corrections' is not available due to lazy='raise_on_sql'`. **Verde** |

E a decisão de topo, cobrada na abertura antes de qualquer pergunta nova:
**a regra foi reescrita** (LEARNING-0005). O item da DoD passa a ser sobre as
perguntas *desta* sessão; a fila virou arquivo, com as 11 antigas registradas ao
lado do que a execução demonstrou sobre cada uma.

### Custo (ADR-0010)

| O quê | Execuções | ~US$ |
|---|---|---|
| Comparação v1 vs. v2 (6 casos × 2 braços) | 12 | 0,24 |
| Reteste do caso "ordem das palavras" | 3 | 0,06 |
| Medição de latência no Simulador | 10 | 0,20 |
| Prova ponta a ponta com áudio com erro | 1 | 0,02 |
| **Total** | **26** | **≈ 0,52** |

### Dívidas explícitas

| O que ficou | Gatilho / card |
|---|---|
| **A escala de `severity` foi decidida sem eval** — três níveis é palpite informado pela tela do CARD-016 | Fase 4 (eval): se o modelo usar um dos níveis em <10% das correções, revisitar |
| **`OTHER` pode virar lixeira** da taxonomia | ErrorPattern (pós-MVP) é quem mede a distribuição |
| **Os quatro campos legados** continuam no `/v1` | `/v2`, ou o app mínimo suportado ler `corrections[]` (o `GET /v1/meta` responde) |
| **A medição de latência não exercitou o caminho com correção** — o WAV fixo é uma frase correta, e as 10 execuções deram `corrections: []` (o desfecho certo) | A prova do caminho com correção é o teste contra Postgres real e a execução ponta a ponta acima, não a §12 |
| **`parse_wire` deixou de ser simétrico** — 4 eventos são `**data`, `feedback` não é | O próximo evento com dataclass aninhada; se houver um terceiro, vale um desserializador genérico |
| **Aparelho físico** continua bloqueado | ADR-0048 — `npx expo run:ios --device` |
