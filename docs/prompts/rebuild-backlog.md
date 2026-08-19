# Prompt — Reconstrução do backlog em torno do alvo de produto

- **Tipo:** prompt de sessão, para ser entregue a um agente
- **Escrito em:** 2026-08-19, na sessão de medição de latência
- **Status:** não executado

---

## O alvo — leia isto antes de qualquer outra coisa

O backlog atual (CARDs 001–017) foi escrito para um produto **turn-based de
walkie-talkie**, com orçamento de latência de 12–15 s, sem cobrança, e sob um
eixo de projeto que priorizava o aprendizado do desenvolvedor sobre a entrega.

**Nada disso vale mais.** O alvo agora é:

> **O aluno fala. Em ~1,4 segundos o professor começa a responder em áudio. E o
> aluno paga por isso.**

Três mudanças de fundo, todas registradas em documento e nenhuma opinião sua:

| Eixo | Antes | Agora |
|---|---|---|
| Latência | áudio completo em ≤ 12–15 s | **primeiro áudio em ~1,4 s** |
| Modelo de negócio | projeto pessoal, custo zero | **produto cobrado por assinatura** |
| Prioridade do projeto | aprendizado do desenvolvedor | **crescer o produto**, aprendendo por consequência |

Esta sessão reconstrói o backlog para esse alvo. Ela **não escreve código**.

### A regra de desempate

O desenvolvedor declarou que **performance não é negociável na primeira
entrega**. Isso não é ênfase — é ordem de precedência, e resolve todo conflito
que aparecer durante a reconstrução:

> **Se algo tiver que ceder para caber, cede ESCOPO — nunca latência.**

Na prática: um card que entregaria mais funcionalidade a 3,7 s perde para um card
que entrega menos a 1,4 s. Funcionalidade adiada volta num card seguinte;
latência entregue errada vira retrabalho de arquitetura, porque o pipeline em
cascata **não é um ajuste que se faz depois** — ele muda a forma dos CARDs 007 a
012. É a diferença entre construir para streaming e converter para streaming.

Corolário para o corte de escopo do MVP: se a fatia vertical não couber inteira,
corte **features**, não etapas do pipeline.

---

## O que o alvo de 1,4 s significa tecnicamente

Isto não é aspiração: está medido e derivado em
[`docs/analise-caminho-para-1-2s.md`](../analise-caminho-para-1-2s.md).

| Etapa | Hoje (batch, medido) | Alvo (cascata) |
|---|---|---|
| STT (`mlx-whisper base.en`, 17,6 s de fala) | 0,20 s | 0,20 s |
| LLM | 1,86 s (JSON completo) | **~0,8 s** (até fechar a 1ª frase) |
| TTS | 1,68 s (resposta inteira) | **0,41 s** (1ª frase) |
| **Até o primeiro áudio** | **3,74 s** | **~1,4 s** |

O mecanismo é **a cascata**: o LLM responde em *streaming*, o parse extrai
`spoken_reply` frase a frase, e cada frase vai para o TTS e para o aluno enquanto
o resto ainda está sendo gerado.

### Duas fronteiras que você NÃO deve cruzar

1. **Isto não é realtime, e o V2 não deve ser antecipado.** A cascata não precisa
   de WebSocket, VAD, barge-in nem módulo nativo de áudio. Um agente com uma meta
   de 1,4 s na mão tende a propor a pilha realtime inteira — o documento §2
   explica em detalhe por que isso *adiciona* trabalho em vez de economizar:
   o V2 substitui transporte e orquestração, **não a fundação**, e hoje não
   existe V1 para pular.
2. **1,4 s é o *primeiro áudio*, não o turno completo.** A resposta típica tem
   **17 s de áudio** para tocar. Turno completo em 1–2 s é fisicamente impossível
   e nenhum card deve prometê-lo.

### O que a cascata NÃO entrega, e precisa estar escrito no backlog

**Interrupção (barge-in).** O aluno falar por cima do professor exige VAD durante
playback, supressão de eco e cancelamento de geração em voo. Isso é V2 de
verdade. Um produto com 1,4 s de primeiro áudio **sem** barge-in ainda é um
walkie-talkie — só que ágil. Seja honesto sobre isso nos cards.

---

## As duas decisões pendentes que travam parte do trabalho

O desenvolvedor confirmou o alvo. Duas consequências dele **precisam de um "ok"
explícito na abertura da sessão**, antes de você escrever os cards que dependem
delas:

1. **Reordenar os campos do JSON do professor** para `spoken_reply` vir antes de
   `tip` e `translation_pt`. **Sem isso a cascata não funciona** — a primeira
   frase falada só sai depois de o modelo gerar tudo que vem antes dela. O prompt
   do professor está congelado até o eval (Fase 4), mas a *ordem dos campos* não
   é conteúdo pedagógico. A linha é do desenvolvedor: pergunte e siga.
2. **Reabrir ADR-0016 e ADR-0006.** São consequência necessária (o áudio deixa de
   ser um objeto só). Pela regra do projeto isso é **ADR novo que substitui**,
   nunca edição do antigo.

Se ele vetar (1), a cascata morre e o alvo volta a ~3,7 s. Nesse caso **pare e
peça nova direção** em vez de reconstruir o backlog para um alvo que não existe.

---

## A mudança de eixo do projeto — e o conflito com o `CLAUDE.md`

**O `CLAUDE.md` ainda declara que o produto é o aprendizado do desenvolvedor e o
código é subproduto.** Isso não vale mais, mas o arquivo é a constituição e a
emenda é dele, não sua.

1. **Não edite o `CLAUDE.md`.** Produza a emenda **em diff**, junto com os cards.
2. Está em jogo, no mínimo: a seção **OBJETIVO**; a **regra do explicador** e o
   `docs/perguntas-em-aberto.md`; o item da **Definition of Done** que exige o
   desfecho do explicador no card; e o campo **"Objetivo de aprendizado"**, hoje
   obrigatório em `docs/backlog/CARD-000-template.md` (proposta: substituir por
   **"Por que agora"**, amarrando o card ao caminho de produto).
3. **Enquanto a emenda não for aceita, o `CLAUDE.md` vigente vence.** Se precisar
   violá-lo para entregar, **pare e pergunte**.

### O que NÃO é cerimônia e sobrevive à virada

Não confunda "menos cerimônia de aprendizado" com "menos rigor". **Ficam, e ficam
mais importantes:** os quality gates (ADR-0015/0019 — `ruff`, `mypy --strict`,
`lint-imports`, `pytest --cov`); os ADRs com o critério escrito de
`docs/adr/README.md`; a arquitetura em camadas com portas (ADR-0012/0003 — ela
existe porque permite trocar provider, e trocar provider virou alavanca de custo
e de latência); os post-mortems.

Sai a **verificação pedagógica**. Fica a **verificação de engenharia**.

---

## O que ler, nesta ordem

1. **`docs/analise-caminho-para-1-2s.md`** — o alvo, o mecanismo, o custo, as
   fronteiras. É o documento que define esta sessão.
2. **`docs/medicao-latencia.md`** — todos os números medidos. Preste atenção
   especial à **§3.4** e à **§7** (o que os números **não** decidem).
3. **`docs/analise-custo-e-precificacao.md`** — a economia unitária, as margens e
   o achado da unidade da cota.
4. `docs/adr/0021-...` — decisão em vigor sobre caching. O **ADR-0020 está
   substituído**; leia só como histórico.
5. `CLAUDE.md` — inteiro, sabendo que a seção OBJETIVO está em disputa.
6. `docs/backlog/README.md` e os CARDs **001–017** — o que existe hoje.
7. `docs/visao-produto-e-arquitetura-alvo.md` — §A (MVP), §D (arquitetura) e §F
   (anti-overengineering, com os gatilhos). **O orçamento de latência da §D está
   obsoleto**; o resto vale.
8. ADRs **0001, 0002, 0003, 0005, 0006, 0008, 0010, 0011, 0014, 0016** — o que
   está decidido e você não contradiz sem ADR novo.
9. `docs/roadmap.md` — o sequenciamento em fatia vertical e por que ele é assim.

---

## O estado real do código — a armadilha central

**Existe:** domínio (`Turn`, `Session`, `Student`), portas de repositório,
adapters de persistência, migrations, health check, quality gates, CI.

**Não existe:** nenhum adapter de IA, nenhum worker, nenhum endpoint de Turn,
nenhum app. **Nada do produto funciona ponta a ponta.**

Daí a armadilha: um backlog "voltado a crescimento" tende a inchar com features
(streaks, gamificação, CEFR, social) sobre um produto que não roda. **Crescer o
produto hoje é fazê-lo funcionar ponta a ponta e cobrar por isso.** Qualquer card
que não sirva ao caminho *"aluno fala → ouve em ~1,4 s → paga"* precisa de
justificativa explícita ou não entra.

A tabela de gatilhos da **visão §F** continua valendo inteira. Se propuser algo
que ela cortou, mostre que o gatilho foi atingido.

---

## Os achados medidos que reordenam o backlog

Nenhum é opinião; todos estão nos documentos acima.

### A. Latência

1. **A cascata é o mecanismo central** (§ acima). Ela redesenha CARDs 007, 008,
   009, 010 e 012 — não é um ajuste, é o eixo do pipeline.
2. **O worker DEVE manter os modelos residentes.** Carregar por job custa **~6 s
   por turn** (0,42 s de STT + 5,63 s de Kokoro) — mais que todo o resto somado.
   Detalhado na seção própria abaixo.
3. **`mlx-whisper` é 2,4–2,8× mais rápido que `faster-whisper`**, e é **Apple
   Silicon apenas**. Não é trocar o default: é ter **dois adapters**, com o
   default dependendo de onde o worker roda.
4. **`int8` é mais lento que `float32` neste hardware** (1,48 s → 1,18 s ao
   *abandonar* a quantização). Não adote `int8` por hábito.
5. **A escolha de modelo do STT está BLOQUEADA.** As 16 variantes deram 100% de
   concordância porque o áudio de teste era TTS sintético — o caso trivial.
   Latência está medida; **qualidade não**. O CARD-006 precisa de insumo com voz
   real de aprendiz antes de fixar modelo.
6. **O Kokoro traz três dependências escondidas** (medição §4.3): `espeakng-loader`
   com caminho de CI compilado dentro do binário; conserto exige `espeak-ng` de
   sistema apontado **depois** do import; e spaCy com `en_core_web_sm` não
   declarado. É dependência de sistema — vai para o Dockerfile, não para o
   `pyproject.toml`. **Argumento para avaliar o Piper antes de fixar o Kokoro.**

### B. Custo e negócio

7. **100% do custo variável é o LLM** (~US$ 0,004/turn), meio a meio entre
   entrada e saída. Infra é irrelevante na escala.
8. **Comissão de loja (15–30%) é ~4× o custo de IA.** O canal de cobrança é
   decisão arquitetural de primeira ordem, e o app web (ADR-0002) deixa de ser
   companion e vira candidato a canal de receita.
9. **A margem quebra no usuário pesado:** 4,4× no casual, **3,0× no engajado**,
   **1,49× no pesado**. O **CARD-015 (quotas + kill switch) passa de higiene a
   bloqueante de lançamento comercial** — hoje ele está na Fase 5, tarde demais.
10. **A unidade da cota diverge do driver de custo em 3×.** O domínio modelou
    cota em **minutos falados** (`Turn.audio_duration`), mas o custo é **por
    chamada ao LLM**: 100 turns curtos custam 3× mais que 20 turns longos com os
    mesmos 10 minutos. Escopo do CARD-015; afeta o domínio.
11. **Prompt caching não engata** — limiar medido de **4.096 tokens**, que uma
    conversa deste produto não alcança (ADR-0021). O CARD-007 **não** implementa
    caching, mas o **CARD-014 (`UsageEvent`) continua tendo de registrar as três
    contagens de entrada** — é o instrumento que detecta a mudança de regime.
12. **Cobrar é premissa que contradiz o objetivo escrito** e ainda não foi
    formalizada em documento de visão. Confirme com o desenvolvedor antes de
    escrever cards de cobrança.

### C. Residência dos modelos no worker — a decisão mais madura da lista

Já medida, já decidida, ainda gratuita. O backlog tem de garantir:

1. **Carga uma vez, na subida do worker** — em `arq`, o hook `on_startup`
   populando o `ctx` compartilhado. O equivalente mental é um singleton no DI do
   host de um `BackgroundService`, não um `new` dentro do `ExecuteAsync`.
2. **O readiness (ADR-0014) precisa distinguir "subiu" de "pronto".** Worker que
   pega job durante a carga paga os ~6 s que a decisão existe para evitar.
3. **Todo restart custa ~6 s de indisponibilidade** — consequência aceita, que
   muda o desenho de deploy.
4. **~1–2 GB residentes viram requisito documentado** — é o número que dimensiona
   qualquer máquina, hoje ou hospedada.
5. **Se o `mlx-whisper` vencer, a conta muda:** a carga dele **não foi medida em
   separado**. O grosso dos 6 s é o Kokoro de qualquer forma.

**Exige ADR** — critério 5 ("difícil de reverter": mexe em ciclo de vida do
worker, readiness e deploy). Não existe ainda.

### D. O que os números NÃO cobrem

- **Custo de composição:** serialização e cópia de áudio entre etapas, contenção
  de CPU entre STT e TTS, GIL, pickup da fila, upload do cliente, latência de
  descoberta. Só existe depois do CARD-009; o CARD-012 já o exige.
- **Máquina hospedada:** tudo foi medido num Apple M4. Em x86 sem Neural Engine
  o `mlx-whisper` **não roda** e os demais números não transferem.

---

## O estado dos ADRs — auditoria feita, não repita o trabalho

**Editar ou apagar ADR está proibido** pela regra do próprio projeto
(`docs/adr/README.md`): ADR aceito registra *por que se decidiu aquilo com a
informação daquele momento*, não o que é verdade hoje. Quando uma decisão cai,
escreve-se um **sucessor** e marca-se o antigo como substituído. Foi assim com o
ADR-0020 hoje.

Auditoria dos 21 ADRs contra o alvo novo:

| ADR | Situação |
|---|---|
| 0001 WhatsApp descontinuado | ✅ vale |
| 0002 Expo + web separada | ✅ vale, e **ganha peso**: a web vira candidata a canal de receita |
| **0003 V1 turn-based → V2 realtime** | ✅ **vale e é reforçado.** Não substitua. A cascata é a **costura 4** que ele já mandava pagar ("pipeline como passos componíveis… o V2 rearranja os mesmos passos em modo streaming"). Fazer a cascata **cumpre** o ADR-0003, não o contraria |
| 0004 Postgres/SQLAlchemy/Alembic | ✅ vale |
| 0005 arq sobre Redis | ✅ vale, **ganha requisito**: carga de modelos no `on_startup` |
| **0006 storage S3 com URL assinada** | ⚠️ **precisa de sucessor** — mídia deixa de ser um objeto por turn e vira chunks |
| 0007 auth JWT + refresh | ✅ vale |
| 0008 contrato /v1 aditivo | ✅ vale, e **restringe**: a entrega progressiva não pode quebrar cliente antigo que trate o payload de forma exaustiva |
| 0009 estratégia de modelos de IA | ✅ vale |
| 0010 política de custo | ⚠️ **em tensão** com a premissa de cobrança (ainda não confirmada). A base de projeção já foi revista. Só vira sucessor se o desenvolvedor formalizar a monetização |
| 0011 STT/TTS locais | ✅ vale, mas **incompleto**: não cobre o adapter duplo `mlx-whisper`/`faster-whisper` |
| 0012 regra de camada executável | ✅ vale |
| 0013 configuração tipada | ✅ vale |
| **0014 health check** | ⚠️ **precisa de extensão**: o readiness do worker tem de distinguir "subiu" de "pronto" (modelos carregados) |
| 0015 quality gates | ✅ vale |
| **0016 ciclo de vida do Turn** | ⚠️ **precisa de sucessor** — áudio parcial quebra a premissa de que a etapa é derivável de artefatos completos |
| 0017 erro de domínio / Result | ✅ vale, e **ganha um caso de uso**: falha depois de entrega parcial |
| 0018 testcontainers | ✅ vale |
| 0019 limiar de cobertura | ✅ vale |
| 0020 prompt caching | ⛔ já substituído pelo 0021 |
| 0021 caching adiado | ✅ vigente |

**Leitura:** de 21 ADRs, **dois precisam de sucessor** (0006 e 0016), **um precisa
de extensão** (0014), **um está em tensão** aguardando decisão de produto (0010) e
**um está incompleto** (0011). O resto sobrevive intacto — inclusive o 0003, que é
o que mais parecia ameaçado e é justamente o que autoriza a cascata.

---

## Entregáveis

### 1. Diagnóstico do backlog atual, card a card

Tabela com os 17 cards e, para cada um: **mantém / reescreve / reprioriza /
divide / mata**, com uma linha de motivo ancorada num achado ou ADR. Card que
você não vai tocar também aparece, dizendo por quê.

### 2. O backlog reconstruído

No formato de `docs/backlog/CARD-000-template.md`, com o campo de aprendizado
tratado conforme a emenda proposta. Cobrindo no mínimo:

**Pipeline em cascata** (o coração desta reconstrução):

- **CARD-006 (STT)** — adapter batch; **dois adapters** (`mlx-whisper` e
  `faster-whisper`) com seleção por config; escolha de modelo **bloqueada** até
  haver áudio de aprendiz; não assumir `int8`.
- **CARD-007 (LLM)** — resposta em **streaming** e **parse incremental** que
  libere `spoken_reply` frase a frase. Este é o card tecnicamente mais difícil da
  reconstrução: extrair um campo de um JSON que ainda está sendo gerado. Avalie
  explicitamente as opções (structured outputs com streaming; reordenar o schema
  e usar parser tolerante; duas chamadas separadas) e **registre o trade-off** —
  não escolha em silêncio.
- **CARD-008 (TTS + storage)** — síntese **por sentença**, storage e URL assinada
  **por chunk**; avaliar Piper contra Kokoro à luz do achado 6.
- **CARD-009 (worker)** — pipeline como **cascata**, não cadeia sequencial;
  modelos residentes (seção C); e o **caminho triste do turn parcialmente
  entregue** — falha depois de o aluno já ter ouvido dois trechos. O
  `Turn.fail()` atual não modela isso.
- **CARD-010 (endpoints)** — entrega **progressiva**. Avaliar SSE contra polling:
  polling entrega áudio em chunks de forma desconfortável, e a §F tinha cortado
  WebSocket com gatilho — SSE é mais barato e o gatilho mudou.
- **CARD-012 (cliente)** — **playback encadeado** dos chunks, sem buraco audível
  entre frases; medição ponta a ponta.

**Comercial** (não existe nenhum card disso hoje):

- planos, assinatura, entitlements, webhooks de pagamento;
- **canal de cobrança** (loja vs. web) — vale 11–26 pontos de margem;
- **CARD-015 repriorizado como bloqueante**, com a unidade da cota decidida;
- **CARD-014 (`UsageEvent`)** antecipado — é pré-requisito do kill switch.

### 3. A ordem, com dependências explícitas

O sequenciamento atual (001 → 002/003 → 005 → 009 → 010 → 012) foi decidido com
dependências pensadas. **Se mudar a ordem, mostre a dependência que justifica.**
O entregável é um **caminho crítico até "o produto roda ponta a ponta em ~1,4 s e
cobra"**, não uma lista.

### 4. Os ADRs que faltam

Conferidos contra "Quando um ADR é OBRIGATÓRIO" de `docs/adr/README.md`,
**citando o critério**:

- **substituir ADR-0016** — ciclo de vida do Turn com áudio parcial;
- **substituir ADR-0006** — mídia em chunks, chaves e URLs assinadas por trecho;
- **transporte de entrega progressiva** (SSE vs. polling) — critério 2;
- **residência dos modelos no worker** (seção C) — critério 5, o mais maduro;
- **adapter duplo de STT** e como o default é escolhido — critério 2;
- **canal de cobrança e provedor de pagamento** — critérios 1 e 3;
- **unidade da cota** (minutos vs. turns) — critério 2, afeta o domínio.

Escreva ou apenas proponha, conforme o desenvolvedor preferir — **pergunte**.

### 5. A emenda ao `CLAUDE.md`, em diff

Proposta, não aplicada.

---

## Restrições

- **Não escreva código de produção.** É sessão de backlog.
- **Não edite o `CLAUDE.md`** sem aceite explícito.
- **Não contrarie ADR aceito em silêncio.** ADR novo que substitui, com o status
  do antigo atualizado — nunca edição do antigo.
- **Não antecipe o V2** (realtime, VAD, barge-in, WebSocket, módulo nativo). O
  gatilho do ADR-0003 continua escrito e nenhuma das três condições foi atingida.
- **Não trate a premissa de cobrança como confirmada** até o desenvolvedor
  confirmar (achado 12).
- **Custo zero de infra** (ADR-0010) continua valendo até que um ADR novo mude.
- Branch própria; `main` é protegida. Commit **nunca** leva trailer
  `Co-Authored-By` ([LEARNING-0001](../learnings/0001-commit-com-coautoria-indesejada-do-agente.md)).
  **Não pushe nem abra PR sem perguntar.**
- Responda em português. O desenvolvedor é sênior em C#/.NET (DDD, CQS/CQRS,
  Result, EF Core, RabbitMQ, Redis, OpenTelemetry) e iniciante em Python — ao
  citar biblioteca, diga qual, por que ela e não a alternativa, e o equivalente
  mental em .NET. Sem aula de injeção de dependência, repositório ou camadas.

---

## O que este prompt deliberadamente não faz

- **Não manda cortar rigor.** A virada é de eixo, não de padrão.
- **Não presume que o backlog atual está ruim.** Boa parte sobrevive com ajuste;
  a cascata é o que força reescrita real, e só nos cards 007–012.
- **Não decide** sobre monetização, canal de cobrança, unidade de cota, nem sobre
  mover STT/TTS para o aparelho (opção registrada em
  `analise-custo-e-precificacao.md` §11, cuja rejeição expirou com a virada de
  eixo e que **precisa ser reapresentada ao desenvolvedor**, não decidida por
  você).
- **Não deixa inventar features.** Crescer o produto, hoje, é fazê-lo funcionar
  ponta a ponta, rápido, e cobrar.
