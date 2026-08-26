# Prompt — CARD-013: a correção deixa de passar e vira dado

- **Tipo:** prompt de sessão, complemento de `/executa-card 013`
- **Escrito em:** 2026-08-26, no fechamento do CARD-012 (PR #17)
- **Status:** não executado

> **Este prompt não substitui o `/executa-card`.** Aquele comando carrega o
> protocolo (branch, ordem de leitura, premissas antes do plano, DoD item a
> item, convenção de commit). **Rode `/executa-card 013` e leia isto junto** —
> aqui está o que é específico deste card, a arqueologia já feita, **o que o
> card pede e já está pronto** (§3.2), e as armadilhas que custam um card
> inteiro se descobertas tarde.

---

## 0. Antes do plano: a fila, e o item que fecha vermelho há oito sessões

`docs/perguntas-em-aberto.md` tem **11 perguntas abertas**. Q5 e Q6 foram
dispensadas; as outras nunca tiveram desfecho.

Reapresente **três**, e as três tocam este card de verdade:

| # | Pergunta | Por que é deste card |
|---|---|---|
| **Q9** | Igualdade de `@dataclass`: por que dois objetos da mesma entidade com um campo diferente não são iguais, e por que o Python **proíbe** usá-los como chave de dict/set? | Este card cria a **primeira coleção filha comparada por valor desde os trechos**: `Turn` 1-N `Correction`. O teste de roundtrip vai comparar listas inteiras com um `==` só, e isso só funciona por causa de `frozen=True`. A pergunta está aberta desde o CARD-005 e nunca teve card tão direto |
| **Q7** | O que `Protocol` faz que dispensa um framework de mock, e **em que momento** se descobre que um fake não satisfaz a porta? | `TeacherFeedback` ganha campo, e **todo fake de `TeacherLlm` quebra no mypy no mesmo instante** — o par completo, que já se demonstrou seis vezes sem nunca ter sido respondido |
| **Q11** | Se eu chamar `client.put_object(...)` **direto dentro de uma corrotina**, o que acontece com as outras corrotinas do worker — e como eu provaria isso num teste? | Entra escrita nova no caminho crítico (persistir N correções por turn). A pergunta é a mesma classe: **o que bloqueia o event loop dentro do orçamento de 1,8 s** |

> **Oitava sessão seguida com o item vermelho** — com uma ressalva honesta: no
> CARD-012 as duas perguntas **do ponto da decisão** foram feitas, respondidas e
> verificadas com execução (uma errou, foi reformulada e fechou). O que segue
> vermelho é a **fila antiga**.
>
> A **pendência de topo continua sendo a mesma desde o CARD-009**: decidir se a
> **regra** muda. Ela foi reapresentada em cinco aberturas seguidas sem resposta.
> **Abra esta sessão cobrando essa decisão**, com os três caminhos por escrito
> (manter e responder / reescrever a regra / manter e aceitar o vermelho como
> dívida declarada). É a única linha da fila que se resolve com uma frase, e não
> com mais uma sessão de trabalho.

---

## 1. Por que este é o próximo card

A visão §A diz que **`Correction` é a entidade mais valiosa do produto**. Até
aqui ela só **transita**: nasce no LLM, vira um evento SSE, aparece na tela e
**some**. Nada é guardado.

Isso trava três coisas de uma vez:

- **O histórico** (CARD-016) não tem o que mostrar.
- **A retomada do SSE tem um buraco declarado.** O
  [ADR-0041](../adr/0041-id-estruturado-do-evento-sse-e-retomada-derivada-do-banco.md)
  item 5 diz, com todas as letras, que `feedback` **não volta** na retomada
  porque não é reconstituível — e registra: *"**Gatilho para reabrir:** o
  CARD-013"*. **Este card dispara aquele gatilho.**
- **O padrão de erro recorrente** (ErrorPattern, pós-MVP) não tem insumo.

## 2. O que já está decidido e não se rediscute

- [**ADR-0022**](../adr/0022-ordem-dos-campos-da-resposta-do-professor-e-contrato-de-latencia.md)
  — **a ordem dos campos da resposta do professor é contrato de latência**, não
  de legibilidade. `spoken_reply` vem primeiro porque é o único campo no caminho
  crítico. Ver §4.1: é a armadilha mais cara deste card.
- [**ADR-0030**](../adr/0030-saida-estruturada-em-streaming-por-tool-use-com-deltas-granulares.md)
  — a saída é estruturada por *tool use* com deltas granulares, e o parse é
  **incremental**. Campo novo = parser novo a conferir.
- [**ADR-0008**](../adr/0008-contrato-api-versionamento-e-tipos-gerados.md) —
  **evolução aditiva**. Proibido remover ou renomear campo dentro de `/v1`.
- [**ADR-0031**](../adr/0031-o-que-atravessa-a-porta-do-professor-e-um-fluxo-de-eventos.md)
  — o histórico **entra por parâmetro**; o adapter não guarda estado.
- [**ADR-0035**](../adr/0035-canal-worker-api-por-pubsub-com-o-banco-como-fonte-da-verdade.md)
  — **o banco é a fonte da verdade**; o pub/sub não guarda nada.
- [**ADR-0017**](../adr/0017-erro-de-dominio-e-excecao-result-fica-para-o-caso-de-uso.md)
  **+ [ADR-0039](../adr/0039-result-minimo-para-desfecho-esperado-de-caso-de-uso.md)**
  — invariante violada levanta exceção; desfecho esperado de caso de uso é
  `Result`.
- [**ADR-0046**](../adr/0046-a-forma-do-client-typescript-e-o-contrato-do-sse-no-openapi.md)
  — os cinco payloads do SSE **são tipos gerados** agora. Campo novo no
  `feedback` quebra o `tsc` do app, que é o ponto.

## 3. Arqueologia — verificada no repositório em 2026-08-26

### 3.1 O que existe

- **O pipeline inteiro roda**, com números: p50 de **2,47 s** até o primeiro
  áudio audível no app (`medicao-latencia.md` §11).
- **`TeacherFeedback`** (`application/ports/teacher_llm.py`) tem hoje:
  `spoken_reply`, `has_mistakes`, `original`, `corrected`, `tip`,
  `translation_pt` — **correção em campo texto, herança do protótipo**.
- **O prompt tem só `v1.md`** (`adapters/llm/prompts/teacher/`).
- **`FeedbackPayload`** (`api/schemas/turns.py`) espelha os quatro campos texto e
  **agora está no OpenAPI** (ADR-0046 §5).
- **`Turn` já tem uma coleção filha**: `audio_chunks: list[TurnAudioChunk]`. O
  padrão de entidade filha, mapper e migration **já existe** — copie-o, não
  invente outro.

### 3.2 **Duas coisas que o card pede e que JÁ ESTÃO PRONTAS**

Leia isto **antes de planejar**, ou você vai gastar meio card refazendo o que o
CARD-009 entregou.

| O card diz | A realidade em 2026-08-26 |
|---|---|
| *"Histórico do `TeacherLlm` construído pela application a partir dos últimos N Turns da Session (equivalente do `_trim` do protótipo, agora por query)"* | **Feito no CARD-009.** `TurnRepository.list_by_session(session_id, limit=...)` existe, devolve **só `completed`**, do mais antigo para o mais novo, e `process_turn.py` (~linha 278) já monta a lista de `Utterance` a partir dela, com `history_turns` vindo da configuração. **O estado em memória do protótipo já morreu** |
| *"Testes: reconstrução de histórico com N+2 turns (corta certo)"*, e o critério de aceite *"12 turns e janela de 10 ⇒ exatamente os 10 últimos"* | **Feito também.** `tests/adapters/test_persistence.py` tem `test_list_by_session_corta_os_mais_velhos_e_nao_os_mais_novos` (contra **Postgres real**, ADR-0018) e `test_list_by_session_devolve_so_os_concluidos_em_ordem_cronologica`; `tests/application/test_process_turn.py` tem `test_o_historico_da_sessao_chega_ao_professor`. **Não reescreva** — no máximo confirme que a janela do card bate com a que o teste usa |

## 4. As armadilhas — o que o texto do card não antecipa

### 4.1 `corrections[]` no meio do JSON mata o orçamento de latência

**Esta é a armadilha mais cara deste card, e ela é invisível em teste unitário.**

O ADR-0022 decidiu a ordem dos campos da resposta do professor como **contrato
de latência**: `spoken_reply` primeiro, porque é o único campo no caminho crítico
até o aluno ouvir alguma coisa. O parse é incremental (ADR-0030) e a cascata
começa a sintetizar **enquanto o resto ainda está sendo gerado**.

Trocar `original`/`corrected`/`tip` (três strings curtas) por um **array de
objetos** aumenta o que o modelo gera. Se `corrections[]` cair **antes** de
`spoken_reply` fechar, o primeiro trecho de áudio atrasa — e o número que o
CARD-012 acabou de medir (2,47 s) piora **sem que nenhum teste fique vermelho**.

**Decida isto no plano:** `corrections[]` vai **depois** de `spoken_reply`, e o
teste que prova isso é de **ordem de emissão**, não de conteúdo. E **meça de
novo** com a rota `/medicao` do app — o instrumento já existe.

### 4.2 O contrato é aditivo: os campos velhos NÃO saem

O ADR-0008 proíbe remover ou renomear campo dentro de `/v1`, e a restrição dura
que o motivou é o app na loja que não atualiza quando queremos.

Então `has_mistakes`, `original`, `corrected` e `tip` **continuam existindo** no
`FeedbackPayload` e no `GET`, ao lado de `corrections[]`. Você vai querer
apagá-los — não apague. **Escreva no ADR quando eles morrem** (provável: `/v2`,
ou quando o app mínimo suportado já ler `corrections[]`, o que o
`GET /v1/meta` sabe responder).

Corolário incômodo e que precisa de decisão: **quem preenche os campos velhos
quando houver 2 correções?** A primeira? A mais severa? Uma concatenação? Não há
resposta óbvia, e responder "a primeira" em silêncio é como o contrato passa a
mentir.

### 4.3 O gatilho do ADR-0041 disparou — e isso é trabalho, não nota de rodapé

Assim que a correção for persistida, o `feedback` passa a ser **reconstituível do
banco**, e o ADR-0041 item 5 deixa de valer. Consequências reais:

- a função `posicao()` e a costura do histórico em `stream_turn_events.py`
  precisam passar a emitir `feedback` na retomada;
- **existe um teste que afirma que ele NÃO aparece no histórico** —
  `test_o_historico_nao_reconstroi_feedback` em
  `tests/application/test_stream_turn_events.py`, que assere
  `all(d.event_id != "feedback" for d in historico(turn))`. Ele vai ficar
  vermelho, e isso é o gate funcionando, não regressão;
- o cliente já deduplica por id (ADR-0041 item 3), então a mudança é do lado do
  servidor.

**Isso é ADR** (critério 2 — fronteira: muda o que a retomada entrega), e o
ADR-0041 precisa ser marcado como completado/ajustado, não editado em silêncio.

### 4.4 `severity` é enum fechado, e o rótulo em pt-BR **não** mora no domínio

O card já decidiu: enum pequeno e estável, porque a UI apresenta severidade em
**palavras** ("pequeno ajuste", "vale revisar"). A tradução é **apresentação** e
mora no cliente (CARD-016).

A armadilha é a de sempre com enum que vai para o banco **e** para o JSON: use
`StrEnum` (o projeto já usa em `TurnStatus`), e lembre que **acrescentar valor a
enum é aditivo e permitido; renomear não é** (ADR-0008).

### 4.5 Persistir N correções entra no caminho crítico de 1,8 s

O worker hoje escreve `Turn` e `TurnAudioChunk`. Agora escreve mais N linhas por
turn. O ADR-0034 mediu o que uma chamada síncrona faz com o event loop (**122 ms
de congelamento**, heartbeat com **zero** voltas).

A pergunta que o plano tem de responder: **em que momento do pipeline as
correções são gravadas?** Junto do `feedback` (mais cedo, mais escritas no
caminho crítico) ou no fechamento do turn (mais tarde, e some se o turn falhar
depois)? Note que a segunda opção interage com o ADR-0023 item 6 — *trecho
entregue não é apagado por falha posterior*.

### 4.6 Mudar prompt sem eval é risco que o próprio card assume

O card diz: manter `v1.md` e `v2.md` lado a lado e comparar manualmente com casos
fixos. **Faça isso de verdade** — com os mesmos insumos, e o resultado escrito.
É a última mudança de prompt antes de existir eval (Fase 4), e o ADR-0021 é o
precedente de registrar o número que **não** deu certo.

## 5. Escopo — o que corta se estourar

- **Não corte:** `corrections[]` tipadas persistidas, o enum de `severity`, a
  aditividade do contrato (§4.2), e a reabertura do ADR-0041 (§4.3).
- **Pode virar card próprio:** a UI (já é CARD-016), agregações/ErrorPattern (já
  tem gatilho pós-MVP), o eval do prompt (Fase 4).
- **Se a latência piorar:** **não esconda.** Meça com a rota `/medicao`, escreva
  o número real e o que dominou. Foi assim que o ADR-0021 nasceu, e foi assim que
  o CARD-012 reportou os 70 ms que faltaram.

## 6. Governança

1. **Item de ADR da DoD** — confira contra `docs/adr/README.md` e **cite o
   critério** (LEARNING-0003). Candidatos já visíveis:
   - **critério 2** — `Correction` no domínio + tabela + `corrections[]` no
     `GET` e no evento SSE: fronteira de dados persistidos e de API;
   - **critério 2** — a retomada passar a incluir `feedback` (§4.3), que
     **completa o ADR-0041**;
   - **critério 5** — migration sobre uma tabela nova com relacionamento;
   - **critério 3** — se o prompt v2 mudar o consumo de tokens de forma
     mensurável.
2. **A skill `voicecoach-arquitetura` é de consulta obrigatória** (é card de
   backend). Regra que não bater com o código é ADR novo ou bug — nunca
   afrouxamento em silêncio.
3. **Decisão que os ADRs não cobrem vai ao desenvolvedor ANTES da primeira linha
   de código.** Nesta sessão são pelo menos três: quem preenche os campos velhos
   com 2 correções (§4.2), quando as correções são gravadas (§4.5), e os valores
   do enum de `severity` (§4.4).

## 7. Definition of Done específica deste card

Além da DoD do `CLAUDE.md`:

- [ ] **2 correções ⇒ 2 `Correction` persistidas** ligadas ao Turn, com enum
      válido, provado por roundtrip contra Postgres real (ADR-0018).
- [ ] **Janela de histórico** — ✅ **já provada** por
      `test_list_by_session_corta_os_mais_velhos_e_nao_os_mais_novos` (§3.2).
      Marque como cumprido **citando o teste**, não escrevendo outro.
- [ ] **Contrato aditivo verificado**: os quatro campos velhos continuam lá, e
      está **escrito** quem os preenche quando há mais de uma correção.
- [ ] **Tipos regenerados e o app compilando** — é o CI que prova (job "contrato
      OpenAPI e tipos TypeScript").
- [ ] **`feedback` volta na retomada**, com o teste antigo invertido e o ADR-0041
      atualizado.
- [ ] **Latência remedida** com a rota `/medicao` e comparada com os **2,47 s**
      da §11 da medição. Se piorou, o número real está escrito.
- [ ] **v1 e v2 do prompt comparados** com casos fixos, resultado escrito.
- [ ] Q9, Q7 e Q11 reapresentadas na abertura, com desfecho registrado
      (respondida / dispensada / em aberto) — **e a decisão sobre a regra (§0)
      cobrada antes de qualquer pergunta nova**.
- [ ] Card atualizado e `docs/backlog/README.md` atualizado.

## 8. Restrições

- **Branch própria** a partir de `main` (com o CARD-012 mergeado — PR #17).
  `main` é protegida. **Confira `git branch --show-current` depois de criar a
  branch**: no CARD-011 dois commits caíram em `main` apesar de o `git switch -c`
  ter reportado sucesso.
- Commit **nunca** leva trailer `Co-Authored-By`
  ([LEARNING-0001](../learnings/0001-commit-com-coautoria-indesejada-do-agente.md)).
- **Não pushe nem abra PR sem perguntar.**
- **Custo:** cada execução do pipeline com `claude-haiku-4-5` real custa
  ~US$ 0,02. A comparação v1×v2 e a remedição de latência multiplicam isso —
  **declare o total no card** (ADR-0010).

### Como subir o ambiente inteiro (conferido no CARD-012)

```bash
docker compose up -d
cd backend && uv run alembic upgrade head
(cd backend && uv run uvicorn voicecoach.api.app:create_app --factory --host 0.0.0.0 --port 8000 &)
(cd backend && uv run voicecoach-worker &)
cd apps/mobile && pnpm expo start
```

> **Cuidado com processos velhos:** no CARD-012 uma API e um worker de sessões
> anteriores ficaram de pé e serviram código antigo por um bom tempo, com o
> sintoma de latências absurdas. `ps aux | grep -E "uvicorn|voicecoach-worker"`
> antes de medir qualquer coisa.

### Verificação visual

O **aparelho físico está bloqueado pelo canal** (ADR-0048): o Expo Go da App
Store está no SDK 54 e o projeto no 57. A verificação corrente é no **Simulador**,
e a saída, quando a dívida for cobrada, é `npx expo run:ios --device`.

Para acompanhar durante a sessão:

```bash
xcrun simctl boot "iPhone 17 Pro" && open -a Simulator
xcrun simctl openurl booted "exp://127.0.0.1:8081"
xcrun simctl io booted screenshot /tmp/estado.png
```

A medição roda sozinha, sem toque:
`xcrun simctl openurl booted "exp://127.0.0.1:8081/--/medicao?execucoes=10&auto=1"`

- Responda em português. O desenvolvedor é **sênior em C#/.NET** e **iniciante
  em Python**: nada de explicar DDD, repositório ou camadas; **sempre** explicar
  qual biblioteca Python resolve o quê e por que ela, e **parar para explicar em
  3 linhas** qualquer idioma sem paralelo em C# — neste card, provavelmente:
  `StrEnum` indo para o banco e para o JSON sem conversor, a igualdade estrutural
  de `@dataclass(frozen=True)` numa coleção filha, e o `relationship` do
  SQLAlchemy com carregamento explícito.
