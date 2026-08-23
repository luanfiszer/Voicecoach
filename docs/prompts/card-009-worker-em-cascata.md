# Prompt — CARD-009: worker em cascata, modelos residentes e o caminho triste

- **Tipo:** prompt de sessão, complemento de `/executa-card 009`
- **Escrito em:** 2026-08-23, no fechamento do CARD-008 (PR #13, `8635181`)
- **Status:** não executado

> **Este prompt não substitui o `/executa-card`.** Aquele comando carrega o
> protocolo (branch, ordem de leitura, premissas antes do plano, DoD item a
> item, convenção de commit). **Rode `/executa-card 009` e leia isto junto** —
> aqui está só o que é específico deste card, a arqueologia já feita, e as
> **cinco coisas que o card assume e que não existem no repositório**.

---

## 0. Antes do plano: a fila do explicador está em oito, e três são deste card

`docs/perguntas-em-aberto.md` tem **8 perguntas abertas**. Q5 e Q6 foram
dispensadas pelo desenvolvedor; as outras seis nunca tiveram desfecho.
Reapresente **estas três na abertura, antes do plano**:

| # | Pergunta | Por que é deste card |
|---|---|---|
| **Q7** | O que `Protocol` faz que dispensa um framework de mock, e **em que momento** se descobre que um fake não satisfaz a porta? | Este card escreve **fakes de todas as cinco portas** de uma vez — é o maior exercício de `Protocol` do projeto até aqui, e o critério de aceite exige que o use case rode em milissegundos sem Redis nem Postgres |
| **Q9** | Igualdade de `@dataclass`: por que dois objetos com um campo diferente não são iguais, e por que o Python **proíbe** usá-los como chave de dict/set? | O teste da cascata vai comparar **sequências de eventos publicados** com um `==` só, como o do CARD-007 |
| **Q11** | Se eu chamar `put_object` direto dentro de uma corrotina, o que acontece com as outras corrotinas — e como eu provaria num teste? | O CARD-008 a demonstrou (122 ms de event loop congelado, heartbeat com **zero** voltas) e o CARD-009 é onde a resposta **importa de verdade**: aqui há dois modelos de IA, um banco e um storage disputando o mesmo event loop |

> **É a quarta sessão seguida em que as perguntas se demonstram sozinhas e o
> item da DoD fecha vermelho.** Se acontecer de novo, o CLAUDE.md pede
> postmortem — e o alvo é **a regra**, não a sessão. Considere abrir a sessão
> propondo isso ao desenvolvedor, antes de perguntar qualquer coisa nova.

---

## 1. Por que este é o próximo card

Caminho crítico: `018 → 006 → 007 → 008 → **009** → 010 → 012`. As cinco portas
existem, todas com adapter e teste. **Nenhuma delas jamais foi composta.**

É aqui que o alvo de 1,8 s deixa de ser soma de componentes e vira número real —
e é a primeira vez que o custo de *composição* (contenção de CPU entre STT e TTS,
GIL, cópia de áudio entre etapas) aparece. A §1 da medição avisa há semanas que
esse custo é desconhecido; este card é quem o mede.

---

## 2. O que já está decidido e não se rediscute

- [**ADR-0025**](../adr/0025-modelos-residentes-no-worker-e-readiness-que-distingue-pronto.md)
  — modelos no `on_startup` do `arq`, `ctx` compartilhado, chave
  `voicecoach:worker:ready` com heartbeat, readiness que distingue "subiu" de
  "pronto". **Leia o status dele antes:** a decisão continua inteira, mas o
  número que a motivou encolheu (§3.3 abaixo).
- [**ADR-0031**](../adr/0031-o-que-atravessa-a-porta-do-professor-e-um-fluxo-de-eventos.md)
  — a porta do professor devolve `AsyncIterator[TeacherEvent]`. **O item 6 é lei
  neste card:** abandonar o `async for` é o que cancela a geração; engolir
  `GeneratorExit` faz o produto pagar por tokens que ninguém vai ouvir.
- [**ADR-0033**](../adr/0033-o-que-atravessa-a-porta-de-tts-e-pcm-com-a-taxa-junto.md)
  — PCM cru atravessa a porta de TTS; `concat` está pronto em `application`, e
  comprimir é de quem grava (`adapters/tts/encoding.py`).
- [**ADR-0034**](../adr/0034-adapter-s3-sincrono-em-executor-e-retencao-por-tag.md)
  — `boto3` em executor, e a tag de retenção é derivada da chave. Não invente
  parâmetro de retenção no `put`.
- [**ADR-0023**](../adr/0023-ciclo-de-vida-do-turn-com-entrega-em-cascata.md) +
  [**ADR-0028**](../adr/0028-derivacao-da-etapa-do-turn-mora-no-dominio.md) — a
  etapa é derivada e a ordem de avaliação é contrato. `delivered_partially` já
  existe e já é derivado: **não** acrescente coluna.
- [**ADR-0026**](../adr/0026-entrega-progressiva-por-sse-com-polling-como-contrato-de-recuo.md)
  — os **nomes e payloads dos eventos SSE já estão fixados** (`transcribed`,
  `chunk`, `feedback`, `completed`, `failed`). O que ele **não** decide é como o
  worker os entrega à API — ver §4.2, é a decisão mais cara desta sessão.

---

## 3. Arqueologia — verificada no repositório em 2026-08-23

### 3.1 Cinco coisas que o card assume e que NÃO EXISTEM

Leia antes do plano. **Duas delas tornam o pipeline descrito impossível de
escrever como está.**

| O card assume | O que se verificou | Consequência |
|---|---|---|
| O worker **baixa o áudio do aluno** para mandar ao STT | **`MediaStorage` não tem `get`.** Ela tem `put`, `presigned_get_url` e `delete_prefix` — e o docstring dela diz, com todas as letras, que o método de leitura entra *"por extensão, quando o CARD-009 precisar disso, com o motivo escrito"* | **Você é o CARD-009.** Acrescente `get(key) -> bytes` à porta e ao adapter. É trabalho pequeno, mas é **mudança de porta**: decida se cabe no ADR-0034 (não cabe — ADR aceito não se edita para mudar decisão) ou se vira ADR novo/nota. O `AudioInput(data: bytes)` do ADR-0029 é exatamente o que ele deve devolver |
| O professor recebe `history` | **Nada monta esse histórico.** `TurnRepository` tem só `add`/`get`/`update` — não há `list_by_session`, e `Session` não guarda turnos. Sem isso, `respond_streaming(history)` só pode ser chamado com uma lista de um item, e o produto vira um professor com amnésia | **Decisão de escopo, e é do desenvolvedor.** Ou o card acrescenta a leitura do histórico (método novo na porta de repositório + query + teste), ou o card assume "histórico = só o turno atual" e **registra a dívida por escrito**. Não decida sozinho: muda o que o aluno experimenta |
| `arq` é só instalar | **`arq 0.28.0` força `redis` de 8.1.0 para 5.3.1** (`uv pip install --dry-run arq` → `- redis==8.1.0 / + redis==5.3.1`). O `redis` já está no projeto desde o CARD-002, usado pelo readiness | Downgrade de dependência existente é decisão, não detalhe. Verifique se o `check_redis` continua verde, e **registre** — critério 1 de ADR já está acionado pelo `arq` de qualquer forma |
| O worker publica eventos num canal Redis | **Nada existe:** nem canal, nem formato, nem serialização. E o ADR-0026 item 3 exige **retomada por `Last-Event-ID`** | Ver §4.2. Pub/sub e Streams dão respostas diferentes para "retomável", e a escolha errada só aparece quando o app for para background |
| Dockerfile do worker | **Continua não existindo** — o CARD-008 adiou explicitamente para cá, e o critério *"dado o container"* foi reescrito lá com esse gatilho | Agora existe worker para conteinerizar. Pergunte se entra aqui ou vira card próprio; o Piper não tem dependência de sistema, então a imagem é bem mais simples do que era quando isso foi adiado |

### 3.2 O estado do código, conferido

| Fato | Consequência para você |
|---|---|
| `application/` tem **só** `ports/`. Não existe `use_cases/` | Você cria o primeiro. É o primeiro handler CQS do projeto — e o lugar onde o `Result` do ADR-0017 pode finalmente ser cobrado (§4.4) |
| `src/voicecoach/worker/` continua **só com `__init__.py`** — quarto card seguido | Desta vez o consumidor é você. Se `arq` **não** aparecer no diff, o card não foi feito |
| `Turn` já tem todas as transições: `start_processing`, `attach_transcript`, `attach_reply`, `append_audio_chunk`, `attach_reply_audio`, `complete`, `fail` | Você **não** inventa transição nova. `complete()` exige `transcript`, `reply_text` **e** `reply_audio_ref` — e **não** exige trecho nenhum, de propósito |
| `fail()` aceita a partir de `queued` **e** de `processing`, e **não apaga trecho** | O caminho triste do card já está sustentado pela entidade. O que falta é o pipeline respeitá-lo |
| Os chunks **são persistidos** (`turn_audio_chunks`), e o mapper **acrescenta** em vez de reatribuir a lista | Leia `_append_new_chunks` antes de escrever o `update`: a sutileza já foi resolvida uma vez |
| `TurnRepository.update` existe porque **não há change tracking** (ADR-0004) | Toda mudança no `Turn` em memória precisa de `update` explícito. Esquecer não quebra teste de domínio — some no banco |
| `tests/adapters/fakes_llm.py` já tem fake de gerador assíncrono | Reuse. O critério de aceite pede fakes de **todas** as portas; quatro já têm precedente escrito nos testes de `application` |
| Suíte hoje: **165 passed, 91,77% global, núcleo 100%** | O piso é 90% no núcleo e 80% global |
| Marker `slow` significa **coisas diferentes** por arquivo: dinheiro no LLM, CPU/download no STT e TTS | Este card mistura os dois num teste ponta a ponta. Diga no docstring qual custo se está aceitando |

### 3.3 O número que mudou desde que o card foi escrito

O card diz *"carregar por job custa ~6 s (0,42 s de STT + 5,63 s do Kokoro)"* e
*"o primeiro remédio é o mlx-whisper"*. **A primeira metade está obsoleta:** o
CARD-008 trocou o motor de voz (ADR-0032) e a carga do TTS caiu de 5,63 s para
**0,43 s**. O total de subida do worker é ~**1 s**, não ~6 s.

O que isso muda para você, e o que **não** muda:

- **A decisão do ADR-0025 continua de pé.** Modelo residente segue certo: 1 s por
  job ainda é mais que metade do orçamento inteiro de 1,8 s.
- **O critério de aceite "dois jobs seguidos, o segundo sem custo de carga"
  precisa de margem nova.** Com o Kokoro, a diferença entre pagar e não pagar a
  carga era de 6 s — impossível de confundir com ruído. Com 0,43 s, um teste mal
  calibrado passa por acidente. **Recalibre e diga a margem por escrito.**
- **A carga do `mlx-whisper` continua não medida** (ADR-0025, item 7), e agora
  ela é a **maior** parcela da subida. Meça e registre — o card já pede isso.

---

## 4. As armadilhas — o que o texto do card não antecipa

### 4.1 "A síntese da N+1 não espera o envio da N" é onde o card pode virar bug

É o único paralelismo que o card introduz, e ele tem **duas** formas muito
diferentes:

- **pipeline com fila interna** (uma task sintetiza, outra sobe), que preserva a
  ordem por construção;
- **`asyncio.create_task` por sentença**, que **não preserva ordem nenhuma** — e
  a ordem aqui é contrato: `Turn.append_audio_chunk` exige índice **denso e
  crescente** e levanta `OutOfOrderAudioChunkError`. Duas sentenças em voo, a
  segunda terminando primeiro, e o turn explode.

O modo de falha é intermitente e depende do tamanho do texto. Escolha
conscientemente e escreva por quê — e **teste com a segunda sentença terminando
antes da primeira** (fake de TTS com atraso invertido). Se o teste não existir, a
corrida vai aparecer em produção, num turno longo, uma vez a cada dez.

### 4.2 Como o worker fala com a API: pub/sub e Streams não são intercambiáveis

O ADR-0026 fixou os eventos e exigiu **retomada por `Last-Event-ID`**. O canal
entre worker e API é decisão deste card, e as opções não empatam:

- **Pub/sub Redis** é *fire-and-forget*: quem não está conectado no instante da
  publicação **nunca** recebe. Reconexão no meio do turn perde tudo que passou.
- **Redis Streams** guarda, tem id por entrada (que mapeia naturalmente no `id`
  do SSE) e permite ler a partir de um ponto.
- **Nada:** o SSE do CARD-010 lê os trechos **do banco** por polling interno, já
  que o ADR-0023 os persiste. Mais simples, e o ADR-0026 item 3 diz que a
  retomada é *"a partir dos trechos persistidos"* — o que sugere que o banco já
  é a fonte de verdade e o canal serve só para **acordar** o leitor.

**A terceira leitura é a mais fiel ao que os ADRs escreveram, e é a que a visão
§F favorece.** Não decida no meio da implementação: é fronteira entre dois
processos e ADR obrigatório (critério 2). Leve ao desenvolvedor **antes da
primeira linha**.

### 4.3 Sessão de banco por job — o card cita o risco e não dá a saída

Fora do FastAPI não há `Depends`, e o `async_sessionmaker` existe em
`adapters/persistence/engine.py`. Um job que abre sessão e não fecha vaza
conexão até o pool secar — e o sintoma aparece no **décimo** turno, não no
primeiro. Decida onde a sessão nasce (por job, no `ctx`?) e escreva a razão. Em
.NET seria o escopo de DI por mensagem consumida; aqui não há container que faça
isso por você.

### 4.4 O `Result` do ADR-0017 pode finalmente ter dono — ou não

O ADR-0017 deixou `Result` como TBD com gatilho escrito: *"o primeiro desfecho
que é normal do negócio e não bug"*. Este card traz falhas de **infraestrutura**
(STT caiu, provedor fora do ar), que são exceção por decisão já tomada. Quota
estourada é CARD-015, `Idempotency-Key` é CARD-010.

**Conclusão provável: o gatilho NÃO é atingido aqui, e inventar `Result` agora
seria antecipação.** Verifique, e se confirmar, **registre por escrito no card
que o gatilho foi conferido e não se aplica** — é a diferença entre decisão e
esquecimento.

### 4.5 Retry: o card diz "só antes do primeiro trecho", e isso não é do arq

O `arq` tem retry próprio (`max_tries`), que reexecuta a **função inteira**.
Reprocessar um turn que já emitiu áudio faria o professor recomeçar a falar — o
ADR-0030 já proibiu o análogo dentro do adapter de LLM. O `arq` não sabe disso: a
guarda é **sua**, e o lugar natural dela é o começo da task, olhando o estado do
`Turn`. Um turn `completed` re-enfileirado é **no-op**, não erro.

### 4.6 Não implemente o consumidor (de novo)

Este card **não** expõe endpoint nem SSE (CARD-010), **não** grava `UsageEvent`
(CARD-014), **não** aplica quota (CARD-015). Se `fastapi` aparecer no diff de
`worker/`, o escopo vazou. E a regra de camada é executável: `api` e `worker` são
irmãos e **não se importam**.

---

## 5. Escopo — o que corta se estourar

O card já se declara **G, candidato a quebra**. A regra de desempate:
**cede escopo, nunca latência.**

- **Não corte:** a cascata (o `async for` consumindo o professor e disparando o
  TTS por sentença), a residência dos modelos, o caminho triste com trechos
  preservados, e os fakes de todas as portas.
- **Pode virar card próprio:** a varredura de turns travados (o próprio card já
  autoriza), o Dockerfile do worker, a leitura do histórico da sessão (§3.1) e o
  heartbeat de readiness, se o canal de eventos consumir a sessão.
- **Se quebrar em dois**, o corte natural é: (A) use case em cascata + fakes +
  testes em `application`; (B) worker `arq` real, `ctx`, readiness e medição.
  A parte A é testável inteira sem Redis, e é onde mora o valor arquitetural.

---

## 6. Governança

1. **Item de ADR da DoD** (confira contra `docs/adr/README.md` e **cite o
   critério**, LEARNING-0003). Candidatos já visíveis:
   - **critério 1** — `arq` entra, e o `redis` é rebaixado de 8.1 para 5.3;
   - **critério 2** — o canal worker→API (§4.2), e o `get` na porta de storage
     (§3.1);
   - **critério 5** — a forma da cascata: paralelismo entre síntese e upload é
     caro de desfazer depois que houver consumidor.
2. **Skill `voicecoach-arquitetura`:** cobre 0001–0023 e 0030–0034; **0024–0029
   seguem não destilados**. Se ela contradisser um ADR, o ADR ganha e a skill se
   corrige na mesma sessão.
3. **Decisão que os ADRs não cobrem vai ao desenvolvedor ANTES da primeira linha
   de código.** Nesta sessão são pelo menos três: o canal de eventos (§4.2), o
   histórico do professor (§3.1) e o Dockerfile (§3.1).

---

## 7. Definition of Done específica deste card

Além da DoD do `CLAUDE.md`:

- [ ] Teste que prova que **o primeiro trecho é gravado antes de `replied_at`** —
      é a cascata existindo, e é o critério que distingue este card de uma cadeia
      sequencial.
- [ ] Teste com **a segunda sentença terminando antes da primeira** (§4.1), que
      falharia com `asyncio.create_task` solto.
- [ ] Teste de **dois jobs seguidos** com a margem recalibrada para o mundo
      pós-Piper (§3.3), e a margem justificada por escrito.
- [ ] `voicecoach:worker:ready` só existe **depois** da carga, e nenhum job é
      consumido antes.
- [ ] **TTS falhando na 3ª sentença** ⇒ turn `failed`, os 2 trechos anteriores
      **em storage e no banco**, `delivered_partially` verdadeiro, **nenhum
      retry**.
- [ ] Use case testado com **fakes de todas as portas**, sem Redis nem Postgres,
      em milissegundos — e são eles que fecham a Q7.
- [ ] **Medição ponta a ponta registrada** em `docs/medicao-latencia.md` (§10):
      tempo até o primeiro trecho gravado, com o pipeline real. É o primeiro
      número de **composição** do projeto — todos os anteriores são de componente
      isolado, e a §1 avisa que a diferença é desconhecida.
- [ ] **Carga do `mlx-whisper` medida** e registrada (ADR-0025, item 7).
- [ ] `uv run lint-imports` verde, com `arq` nas listas `forbidden` de `domain` e
      `application` **no mesmo commit**. Prove que o gate morde — o par completo.
- [ ] Cobertura: núcleo ≥ 90%, global ≥ 80%. **Está em 100% / 91,77% hoje.**
- [ ] Gatilho do `Result` (ADR-0017) **conferido e o desfecho registrado** (§4.4).
- [ ] Q7, Q9 e Q11 reapresentadas na abertura, com desfecho registrado no card.
      **Item fechado pelo agente com a própria explicação não conta**
      (LEARNING-0004) — e considere propor o postmortem da regra (§0).
- [ ] Card atualizado e tabela de `docs/backlog/README.md` atualizada.

---

## 8. Restrições

- **Branch própria** a partir de `main` (hoje em `8635181`, com o CARD-008
  mergeado). `main` é protegida.
- Commit **nunca** leva trailer `Co-Authored-By`
  ([LEARNING-0001](../learnings/0001-commit-com-coautoria-indesejada-do-agente.md)).
- **Não pushe nem abra PR sem perguntar.** O padrão é o dos PRs #11, #12 e #13:
  título `CARD-XXX: <frase>`, e as seções *O que entra* → *a decisão do ADR* →
  *achados/divergências* → *Gates* (saída real colada) → *Dívidas registradas no
  card* → *Regra do explicador*.
- **Custo:** o teste ponta a ponta com o professor real **gasta dinheiro**
  (~US$ 0,02/execução, `claude-haiku-4-5`). Marque `slow`, diga no docstring que
  o custo é em dinheiro — e prefira o fake no caminho default. STT e TTS locais
  continuam custando zero (ADR-0010/0011/0032).
- **Não antecipe o V2** (ADR-0003): nada de STT incremental nem TTS intra-frase.
  O que este card garante é que **os passos são componíveis**, para que o V2
  rearranje os mesmos passos.
- Responda em português. O desenvolvedor é sênior em C#/.NET e **iniciante em
  Python**: ao citar biblioteca, diga qual, por que ela e não a alternativa, e o
  equivalente mental em .NET. Idioma sem paralelo em C# — **`async for` sobre
  gerador, `asyncio.Queue`, `TaskGroup`, ciclo de vida do `ctx` do arq** — pare e
  explique em 3 linhas. Sem aula de injeção de dependência, CQS ou camadas.
