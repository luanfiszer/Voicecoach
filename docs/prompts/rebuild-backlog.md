# Prompt — Sessão de reconstrução do backlog: a virada de eixo para produto

- **Tipo:** prompt de sessão, para ser entregue a um agente
- **Escrito em:** 2026-08-19, na sessão de medição de latência
- **Status:** não executado

---


## Por que esta sessão existe

O eixo do projeto mudou. Até aqui o `CLAUDE.md` declarava, com todas as letras,
que **o produto era o aprendizado do desenvolvedor e o código era subproduto**.
Não é mais. A prioridade agora é **crescer o produto**, com aprendizado
acontecendo por consequência de construir, não por cerimônia que o verifica.

O backlog atual (CARDs 001–017) foi escrito sob o eixo antigo. Ele não está
errado — está **desalinhado**. Esta sessão o reconstrói sob o eixo novo.

Uma sessão anterior de medição de latência produziu três artefatos que mudam o
que o backlog deveria conter. Eles são o insumo desta sessão e estão listados em
"O que ler".

---

## A mudança de premissa — declare o conflito antes de qualquer coisa

**O `CLAUDE.md` ainda diz o contrário do que esta sessão assume.** Isso é
conflito de fonte de verdade, não detalhe. Trate assim:

1. **Não edite o `CLAUDE.md` por conta própria.** Ele é a constituição; a emenda
   é do desenvolvedor.
2. **Produza a emenda como proposta**, em diff, junto com os cards. Ela precisa
   dizer o que sai, o que fica e o que muda de status. No mínimo isto está em
   jogo:
   - a seção **OBJETIVO** ("prioridade dupla… 1. meu aprendizado real, 2.
     qualidade de engenharia. Velocidade de entrega NÃO é prioridade");
   - a **regra do explicador** inteira e o arquivo
     `docs/perguntas-em-aberto.md`;
   - o item da **Definition of Done** que exige o desfecho da regra do
     explicador registrado no card;
   - o campo **"Objetivo de aprendizado"**, hoje obrigatório em todo card
     (`docs/backlog/CARD-000-template.md`).
3. **Enquanto a emenda não for aceita, o `CLAUDE.md` vigente vence.** Se você
   precisar violar uma regra dele para entregar esta sessão, **pare e pergunte**.

### O que NÃO é cerimônia e deve sobreviver à virada

Um agente apressado vai confundir "menos cerimônia de aprendizado" com "menos
rigor". São coisas diferentes. **Estes ficam, e ficam mais importantes, não
menos:**

- **Os quality gates do ADR-0015 e ADR-0019** — `ruff`, `mypy --strict`,
  `lint-imports`, `pytest --cov`. Produto que cresce quebra mais, não menos.
- **Os ADRs**, com o critério escrito de `docs/adr/README.md`. Decisão sem
  registro é decisão que se reabre toda semana.
- **A arquitetura em camadas com portas** (ADR-0012, ADR-0003) — ela existe
  porque permite trocar provider, e trocar provider virou alavanca de custo.
- **Os post-mortems** (`docs/learnings/`). Erro repetido é o único inaceitável.

O que sai é a **verificação pedagógica** (perguntar ao desenvolvedor para
comprovar que ele entendeu), não a **verificação de engenharia**.

---

## O que ler, nesta ordem

1. `CLAUDE.md` — inteiro, sabendo que a seção OBJETIVO está em disputa.
2. **`docs/analise-custo-e-precificacao.md`** — a economia unitária. É o
   documento mais importante desta sessão.
3. **`docs/medicao-latencia.md`** — os números medidos (STT, LLM e TTS), o
   **veredito do orçamento na §6**, e principalmente a §3.4 e a §7 (o que os
   números **não** decidem).
4. **`docs/analise-caminho-para-1-2s.md`** — a meta de latência que o
   desenvolvedor levantou depois da medição, o que ela custa, e as **três
   decisões pendentes** que travam qualquer card sobre o assunto.
5. **`docs/adr/0021-...md`** — a decisão nova em vigor. O **ADR-0020 está
   substituído**; leia-o só como histórico.
6. `docs/backlog/README.md` e os CARDs **001–017** — o que existe hoje.
7. `docs/visao-produto-e-arquitetura-alvo.md`, em especial §A (MVP), §D
   (arquitetura alvo) e §F (anti-overengineering, com os gatilhos).
8. ADRs **0001, 0002, 0003, 0006, 0007, 0008, 0010, 0011, 0016** — o que já está
   decidido e você não pode contradizer sem ADR novo.
9. `docs/roadmap.md` — o sequenciamento em fatia vertical e por que ele é assim.

---

## O que mudou de fato — os achados que reordenam o backlog

Não são opiniões desta sessão; estão registrados nos documentos acima.

### 1. Cobrar virou premissa — e ainda não está confirmada

`docs/analise-custo-e-precificacao.md` §0 registra que **monetizar contradiz o
objetivo escrito** e que não há nenhum registro anterior de intenção comercial no
repositório. A premissa agora é: **o produto vai ser cobrado**. Confirme isso com
o desenvolvedor **antes** de escrever cards de cobrança — e se ele confirmar,
isso muda o documento de visão, não só o backlog.

### 2. 100% do custo variável é o LLM

Com STT e TTS locais, cada turn custa ~US$ 0,004, meio a meio entre entrada e
saída de tokens. Infra é irrelevante na escala. **Comissão de loja (15–30%) é ~4×
o custo de IA.** Consequência direta: o canal de cobrança é decisão arquitetural
de primeira ordem, e o app web (ADR-0002) deixa de ser companion e vira
candidato a canal de receita.

### 3. A margem quebra no usuário pesado

A 900 turns/mês a margem cai para **1,49×** o custo; acima disso dá prejuízo. O
**CARD-015 (quotas + kill switch) passa de higiene a bloqueante de lançamento
comercial**. Ele está hoje na Fase 5 do roadmap; é cedo demais para lançar sem
ele.

### 4. A unidade da cota diverge do driver de custo — 3× (medido)

O domínio já modelou a cota em **minutos falados**
(`backend/src/voicecoach/domain/turn.py`, campo `audio_duration`), mas o custo é
**por turn**: 100 turns curtos custam **3× mais** que 20 turns longos com os
mesmos 10 minutos falados. (Medido: a fala longa gera resposta 2,7× maior, o que
reduz a divergência de 5× estimado para 3× real.) Decidir isto é escopo do
CARD-015 e afeta o domínio.

### 5. A escolha de modelo do STT NÃO pode ser feita com os dados atuais

`docs/medicao-latencia.md` §3.4: todas as 16 variantes deram 100% de concordância,
inclusive a mais barata — porque o áudio de teste era TTS nativo sintético, o
caso trivial. **Latência está medida; qualidade não.** O CARD-006 precisa de um
insumo com voz real de aprendiz antes de fixar modelo.

### 6. `mlx-whisper` é 2,4–2,8× mais rápido, e é Apple Silicon apenas

Medido. Não é "trocar o default" — é ter **dois adapters**, com o default
dependendo de onde o worker executa. Isso é ADR novo (critério 2, fronteira),
ainda não escrito.

### 6.5. O orçamento de latência é FOLGADO — duas alavancas mudaram de status

Medido ponta a ponta por componente (medição §6): mesmo no **pior** caso o áudio
fica pronto em **~6,6 s** contra um teto de 12–15 s; o texto em **~5,0 s** contra
6 s. Consequências que o backlog precisa absorver:

- **A cascata LLM→TTS por sentença está EM ABERTO** — leia
  [`docs/analise-caminho-para-1-2s.md`](../analise-caminho-para-1-2s.md) antes de
  concluir qualquer coisa sobre ela. Contra o orçamento de 12–15 s ela é
  desnecessária (economiza ~1,3 s numa folga de ~6 s). Mas o desenvolvedor
  levantou uma meta nova — **primeiro áudio em 1–2 s** — e sob essa meta ela vira
  a alavanca principal (~3,74 s → ~1,4 s). **A meta ainda não foi confirmada e
  três decisões estão pendentes** (§8 daquele documento). Não decida por ele.
- **O worker DEVE manter os modelos residentes.** Carregar por job custa **~6 s
  por turn** (0,42 s de STT + 5,63 s de Kokoro) — mais que todo o resto do
  pipeline somado. Sem residência o pior caso vai a **12,69 s** e fura o teto de
  12–15 s; com residência fica em **6,64 s**. Detalhado abaixo, na seção própria.
- O incômodo original com a latência **não é o tempo das etapas**; é o desenho
  turn-based em si, que o ADR-0003 já nomeou e aceitou como degrau para o V2.

### 6.6. Residência dos modelos no worker — a decisão mais concreta desta lista

Esta é a única alavanca desta sessão que já está **medida, decidida e ainda
gratuita**. Ela precisa sair do backlog como requisito, não como sugestão.

**O que o backlog tem de garantir:**

1. **Os modelos são carregados uma vez, na subida do worker**, não por job. Em
   `arq` isso é o hook `on_startup`, que popula o `ctx` compartilhado entre jobs
   — o equivalente mental é um singleton registrado no DI do host de um
   `BackgroundService`, e não um `new` dentro do `ExecuteAsync`.
2. **O readiness do worker (ADR-0014) precisa refletir isso.** Um worker que
   subiu mas ainda está carregando modelos **não está pronto**, e hoje nada
   modela essa diferença. Se o job chegar antes da carga terminar, ou ele espera
   ou ele paga os 6 s que a decisão existe para evitar.
3. **O custo de reinício passa a ser visível:** todo restart do worker custa
   ~6 s de indisponibilidade. Isso entra no card como consequência aceita, e
   muda o desenho de deploy (não se reinicia worker a cada mudança trivial).
4. **Footprint de memória vira requisito documentado** (~1–2 GB residentes) —
   é o número que decide o tamanho de qualquer máquina, hoje ou hospedada.
5. **Se o `mlx-whisper` for escolhido, esta conta precisa ser refeita:** a carga
   dele **não foi medida em separado** nesta sessão (o aquecimento foi
   descartado junto). O grosso dos 6 s é o Kokoro de qualquer forma, mas o
   número exato está em aberto.

**Isto exige ADR** — critério 5 do `docs/adr/README.md` ("seria difícil de
reverter": desfazer mexe no ciclo de vida do worker, no readiness e no deploy) e,
discutivelmente, critério 2 (fronteira: quem é dono do ciclo de vida do modelo).
Ele **não existe ainda** e está na lista do entregável 4.

### 7. `int8` é mais lento que `float32` neste hardware

1,48 s → 1,18 s ao **abandonar** a quantização. O CARD-006 não deve adotar `int8`
por hábito.

### 7.5. O Kokoro traz três dependências escondidas — risco novo no CARD-008

O TTS **não roda out-of-the-box** (medição §4.3): o `espeakng-loader` publica um
binário com caminho de dados de CI compilado dentro; o conserto exige
`espeak-ng` de sistema apontado **depois** do import; e o Kokoro puxa spaCy com
um modelo (`en_core_web_sm`) não declarado. Isso é dependência de sistema
não-Python — vai para o Dockerfile, não para o `pyproject.toml`. É argumento para
**avaliar o Piper antes de fixar o Kokoro**.

### 7.6. O prompt caching foi medido e derrubado

O ADR-0020 (escrito e substituído no mesmo dia) assumia limiar de ~1.024 tokens.
**Medido: 4.096.** Uma conversa deste produto não o alcança, então o caching
**não engata**. O ADR-0021 registra a decisão de adiar e o gatilho para reabrir.
Consequência direta no backlog: **o CARD-007 não implementa caching**, mas o
**CARD-014 (`UsageEvent`) continua tendo de registrar as três contagens de
entrada** — é o instrumento que detecta a mudança de regime.

Consequência na economia: sem essa alavanca, o custo projetado sobe de
US$ 0,002 para **US$ 0,0031/turn**, e a margem do usuário engajado cai para
**3,0×** — no fio da meta. Isso **reforça** o achado 3.

### 8. ⚠️ Uma rejeição que expirou junto com o eixo antigo

`docs/analise-custo-e-precificacao.md` §11 avalia **rodar STT e TTS no aparelho
do aluno** — o que zeraria o compute de servidor e o tráfego de áudio nos dois
sentidos, deixando só o LLM como custo, e cortaria latência de forma dramática.

Ela foi rejeitada com **dois** argumentos. O primeiro (contraria ADR-0003 e
ADR-0011) continua de pé. O segundo era: *"esvazia a prioridade nº 1 do projeto,
porque tira do backend exatamente o que os CARDs 006–009 existem para ensinar"*.

**Esse segundo argumento morreu com a virada de eixo.** O texto do §11 diz
literalmente que é *"a decisão certa para uma startup e a errada para este
projeto hoje"* — e o projeto acabou de virar o primeiro caso.

**Não decida isso sozinho.** Reapresente a alternativa ao desenvolvedor com os
números atualizados e o trade-off honesto (economia e latência de um lado;
retrabalho de CARDs 006/008/009, superfície de cliente muito maior, tamanho do
modelo no aparelho, bateria e qualidade de voz do outro). É provavelmente a
decisão mais cara desta sessão.

---

## A armadilha central — leia antes de planejar

**Um backlog voltado a crescimento tende a inchar.** O erro previsível aqui é
transformar "focar no produto" em vinte cards de features (streaks, gamificação,
níveis CEFR, compartilhamento social, onboarding com IA) e enterrar a fatia
vertical que ainda **não fecha**.

O estado real do código: existem domínio, persistência, migrations e health
check. **Não existem** adapters de IA, worker, endpoints de Turn, nem app. Nada
do produto funciona ponta a ponta ainda.

Portanto: **crescer o produto hoje significa terminar a fatia vertical, não
adicionar features a um produto que não roda.** Qualquer card novo que não sirva
ao caminho "aluno fala → aluno ouve resposta → aluno paga" precisa de
justificativa explícita ou não entra.

A tabela de gatilhos da **visão §F (anti-overengineering)** continua valendo
inteira. Se você propuser algo que ela cortou, é preciso mostrar que o gatilho
dela foi atingido.

---

## Entregáveis

### 1. Diagnóstico do backlog atual, card a card

Uma tabela com os 17 cards e, para cada um: **mantém como está / reescreve /
reprioriza / divide / mata**, com uma linha de motivo ancorada num dos achados
acima ou num ADR. Card que você não vai tocar também aparece, dizendo por quê.

### 2. O backlog reconstruído

Cards no formato de `docs/backlog/CARD-000-template.md`, **com o campo "Objetivo
de aprendizado" tratado conforme a emenda proposta** (se o desenvolvedor mantiver
o campo, preencha-o; se remover, proponha o que ocupa o lugar — sugestão: um
campo **"Por que agora"** amarrando o card ao caminho de produto).

Cobrindo no mínimo:

- **fechar a fatia vertical** (adapters de IA, worker, endpoints, app) —
  ajustada pelos achados 5, 6 e 7;
- **cobrança**: planos, assinatura, entitlements, canal (loja vs. web), webhooks
  de pagamento. **Não existe nenhum card disso hoje**;
- **cota e kill switch** repriorizados como bloqueantes (achados 3 e 4);
- **telemetria de custo** — o `UsageEvent` do CARD-014 é pré-requisito do kill
  switch e do item 5 do ADR-0020, e provavelmente está tarde demais na ordem;
- **telemetria de `usage`** no CARD-007/014 conforme ADR-0021 — **sem**
  implementar caching, mas registrando as três contagens de entrada.

### 3. A ordem, com as dependências explícitas

O sequenciamento atual (001 → 002/003 → 005 → 009 → 010 → 012) foi decidido com
dependências pensadas. **Se você mudar a ordem, mostre a dependência que
justifica** — não reordene por intuição. Um caminho crítico até "o produto roda
ponta a ponta e cobra" é o entregável, não uma lista.

### 4. Os ADRs que faltam

Conferidos contra a lista "Quando um ADR é OBRIGATÓRIO" de
`docs/adr/README.md`, **citando o critério**. Os que já se sabe que faltam:

- adapter duplo de STT (`mlx-whisper` vs `faster-whisper`) e como o default é
  escolhido — critério 2;
- canal de cobrança e provedor de pagamento — critérios 1 e 3;
- unidade da cota (minutos vs. turns) — critério 2, afeta o domínio;
- **residência dos modelos no worker** (§6.6) — critério 5, e é o mais maduro
  da lista: já tem número, já tem decisão, só falta o registro;
- e, se o desenvolvedor reabrir o achado 8, o de STT/TTS no cliente.

Escreva os ADRs ou proponha-os, conforme o desenvolvedor preferir — **pergunte**.

### 5. A emenda ao `CLAUDE.md`, em diff

Como descrito na seção de premissa. Proposta, não aplicada.

---

## Restrições

- **Não edite o `CLAUDE.md`** sem aceite explícito. Proponha em diff.
- **Não escreva código de produção** nesta sessão. É sessão de backlog.
- **Não contrarie ADR aceito em silêncio.** Se um achado derruba um ADR, o
  caminho é ADR novo que o substitui, com o status do antigo atualizado — nunca
  editar o antigo.
- **Não trate a premissa de cobrança como confirmada** até o desenvolvedor
  confirmar (achado 1).
- **Custo zero de infra** continua valendo (ADR-0010) até que um ADR novo o
  mude. Nada de propor cloud paga como se fosse dado.
- Branch própria; `main` é protegida. Commit **nunca** leva trailer
  `Co-Authored-By` ([LEARNING-0001](../learnings/0001-commit-com-coautoria-indesejada-do-agente.md)).
  **Não pushe nem abra PR sem perguntar.**
- Responda em português. O desenvolvedor é sênior em C#/.NET (DDD, CQS/CQRS,
  Result, EF Core, RabbitMQ, Redis, OpenTelemetry) e iniciante em Python — ao
  citar biblioteca, diga qual, por que ela e não a alternativa, e o equivalente
  mental em .NET. Sem aula de injeção de dependência, repositório ou camadas.

---

## O que este prompt deliberadamente não faz

- **Não manda cortar rigor.** A virada é de eixo, não de padrão. Gates, ADRs,
  camadas e post-mortems ficam.
- **Não presume que o backlog atual está ruim.** A maior parte dele
  provavelmente sobrevive com ajuste. Reescrever tudo seria repetir o erro que
  esta sessão quer corrigir, com o sinal trocado.
- **Não decide sobre monetização, canal de cobrança, nem sobre o achado 8.**
  Todas são decisões do desenvolvedor, informadas por você.
- **Não deixa o agente inventar features.** Crescer o produto, hoje, é fazê-lo
  funcionar ponta a ponta e cobrar por isso.
