---
description: Executa um card do backlog seguindo o protocolo de sessão do CLAUDE.md
argument-hint: <número do card, ex.: 002>
---

Vamos executar o card **$ARGUMENTS** do backlog.

> Este arquivo também serve como prompt avulso: para delegar a outro agente,
> copie o conteúdo abaixo trocando `$ARGUMENTS` pelo número do card.

## 1. Branch antes de qualquer coisa

`main` é **protegida** — nunca commite nela. Trabalhe em
`card-$ARGUMENTS-<slug-do-titulo>`; crie a branch a partir de `main` atualizado
se ela ainda não existir, ou faça `git switch` se já existir.

## 2. Leia, nesta ordem, antes de editar qualquer arquivo

1. `CLAUDE.md` — a constituição. Em especial **Regras de trabalho**,
   **Definition of Done** e a **regra do explicador**.
2. `docs/backlog/CARD-$ARGUMENTS-*.md` — o escopo desta sessão. **O que está em
   "Out" não entra**, por mais tentador que pareça.
3. Os **ADRs que o próprio card cita** nas seções Contexto e Dependências —
   cada card lista os seus. Leia também `docs/adr/0012` (regra de camada como
   contrato executável) e `docs/adr/0010` (política de custo), que valem para
   toda sessão.
4. `docs/visao-produto-e-arquitetura-alvo.md` — as partes que o card referencia,
   sempre incluindo a **Parte F (anti-overengineering)**.
5. `backend/README.md` — o mapa de dependências entre camadas, se o card tocar
   o backend. Junto dele, carregue a skill `voicecoach-arquitetura`: é o digest
   operacional dos ADRs (onde mora o quê, o que é proibido em cada camada,
   checklist de PR). Regra da skill que não bater com o código é ADR novo ou
   bug — nunca motivo para afrouxá-la.
6. `docs/learnings/` — **todos**. São erros já cometidos neste projeto; repetir
   um deles é a única falha realmente inaceitável.
7. `docs/referencias/` — análises de projetos de referência, quando houver
   alguma relacionada ao tema do card.

## 3. Declare as premissas e o plano — e espere meu OK

**Antes do plano, abra `docs/perguntas-em-aberto.md`** e me reapresente as
perguntas ainda abertas que tocam o tema deste card (regra do explicador,
LEARNING-0004). O que eu responder fecha a linha lá; o que eu dispensar
permanece registrado.

Antes de criar ou alterar qualquer arquivo (regra das **premissas de escopo**,
origem no LEARNING-0002):

- as **premissas de escopo de produto** de que as suas conclusões dependem, em
  especial o que é permanente vs. andaime — premissa não confirmada é anotada
  como tal no artefato;
- a **árvore de arquivos** que pretende criar ou alterar;
- as **dependências novas** e por que cada uma, com a alternativa descartada;
- **onde cada arquivo novo mora** em relação às camadas, e se isso exige
  ajustar os contratos do import-linter;
- o que você identificou como **armadilha** deste card — a parte que o texto do
  card não antecipa.

Espere minha confirmação. Se quiser, use plan mode.

## 4. Contexto do desenvolvedor (não negociável)

Sou sênior em C#/.NET (DDD, CQS/CQRS, Result, EF Core, RabbitMQ, Redis,
OpenTelemetry) e **iniciante em Python**.

- Não explique injeção de dependência, repositório, unidade de trabalho ou
  camadas — arquitetura eu domino.
- **Sempre** explique qual biblioteca Python resolve o problema, por que ela e
  não a alternativa, e o equivalente mental no mundo .NET.
- Idioma de Python sem paralelo direto em C# (context manager, decorator,
  generator, `async` sem `Task`, duck typing, `Protocol`, dataclass,
  descritor): pare e explique em 3 linhas.

Velocidade de entrega **não** é prioridade. O produto deste projeto é o meu
conhecimento; o código é subproduto.

## 5. Durante a implementação

- **Contratos de arquitetura são lei** (ADR-0012). Dependência nova que não
  pode vazar para dentro entra na lista do contrato `forbidden` **no mesmo
  commit** que a adiciona. `uv run lint-imports` verde não é opcional.
- **Custo zero é requisito** (ADR-0010), não preferência. Nada que exija conta
  paga, tag de imagem fixada, serviço opcional atrás de profile.
- **Não invente convenção** que o repositório ainda não tem: siga o estilo do
  código existente e o que os ADRs já decidiram.
- Se durante a implementação aparecer uma decisão que os ADRs não cobrem,
  **pare e me pergunte** em vez de decidir sozinho e documentar depois.

## 6. Ao final — a Definition of Done, item a item

- [ ] **Critérios de aceite verificados um a um, com evidência real**:
      comando executado e saída de verdade, colada. Descrever o que deveria
      acontecer não conta como evidência. Se um critério não foi atingido, diga
      isso com a saída que prova — relatório honesto vale mais que checklist
      verde.
- [ ] **`uv run lint-imports` verde** (quando o card tocar o backend). Se os
      contratos só passaram porque o código novo é trivial, prove que o gate
      morde: injete a violação, mostre a quebra, reverta.
- [ ] **Item de ADR resolvido contra critério escrito** (regra do
      LEARNING-0003): consulte a lista "Quando um ADR é OBRIGATÓRIO" em
      `docs/adr/README.md` e **cite o critério que se aplicou** — ou registre
      por escrito por que nenhum se aplica. Decisão descrita apenas na seção de
      execução do card **não conta como ADR**: card é registro de trabalho,
      ADR é registro de decisão.
- [ ] **Card atualizado**: status, o que foi entregue, evidência dos critérios
      e **dívidas explícitas** (o que ficou faltando, com o card ou gatilho que
      resolve).
- [ ] **Tabela de `docs/backlog/README.md`** atualizada.
- [ ] **Regra do explicador**: as perguntas foram feitas **no ponto da decisão,
      durante a implementação** (não num bloco no fim) e o **desfecho de cada
      uma** está registrado no card — respondida / dispensada por mim / em
      aberto. Item fechado pelo agente com a própria explicação **não** conta;
      pergunta em aberto entra em `docs/perguntas-em-aberto.md`
      (LEARNING-0004).
- [ ] Nenhuma regra do CLAUDE.md violada.

## 7. Commit

- Commite na branch do card, nunca em `main`.
- **NUNCA** inclua o trailer `Co-Authored-By: Claude` nem qualquer variação com
  nome de modelo (regra do CLAUDE.md, origem no LEARNING-0001). A autoria é
  exclusivamente minha, mesmo quando você redige a mensagem.
- Mensagem de commit explica **o porquê**, não só o quê: qual problema o card
  resolvia, qual decisão foi tomada e o que ficou de dívida.
- **Não faça push nem abra PR sem me perguntar.**

Responda sempre em português.
