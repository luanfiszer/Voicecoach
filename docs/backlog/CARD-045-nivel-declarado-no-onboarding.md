# CARD-045 — O nível declarado pelo aluno entra na conversa

- **ID:** CARD-045
- **Épico:** Qualidade da conversa (briefing 2026-09-09, ponto 5 — feature 1 de 3)
- **Esforço:** M
- **Status:** bloqueado (2026-09-13) — ver "Execução" abaixo
- **Dependências:** CARD-041 (o mecanismo do contexto), ADR-0059

## Contexto

Quinto apontamento do uso real: *a conversa não é adaptada ao nível*.

**Este é o ponto com maior distância entre visão e backlog**, e o briefing o
nomeia sem meias palavras: a visão de produto diz que a estimativa CEFR **entra
no MVP na forma barata** (`visao-produto-e-arquitetura-alvo.md:40`); o
`docs/backlog/README.md:54` a coloca em Fase 7 como "a detalhar"; a docstring de
`domain/student.py:9` diz "Fase 6". Três documentos, três respostas, **zero
cards**. É buraco de planejamento, e o uso real acabou de cobrá-lo.

Das três features que o briefing separou, **esta é a que muda a conversa
amanhã** e é **pré-requisito das outras duas** — ela cria o campo, a tela e o
caminho do nível até o prompt. Decidido em 2026-09-09 que ela e o CARD-046
entram; o mini-teste fica mapeado sem data (CARD-047).

## Problema

`Student` tem `id`, `display_name`, `created_at`. Não tem nível. O prompt do
professor não recebe nível. Não há tela onde o aluno declare nada. O resultado é
que o professor fala igual com um A1 e com um C1 — mesmo vocabulário, mesma
velocidade, mesma tolerância a erro.

## Proposta técnica

O mecanismo é o do **ADR-0059**, criado pelo CARD-041. Este card acrescenta um
campo ao `StudentContext` e **não toca na assinatura da porta** — que é
exatamente o retorno do investimento feito lá.

1. `Student` ganha `cefr_level: CefrLevel | None`, e a migration correspondente.
   **`None` é o estado normal**, não um erro a corrigir: aluno que não declarou
   nada tem a conversa de hoje, sem default inventado. "Supor B1 quando não sei"
   seria pior que não saber (ADR-0059 item 5).
2. `CefrLevel` é enum de domínio (A1…C2). **É escalar aqui, e faixa lá** — o
   declarado é uma escolha do aluno numa lista; a faixa com confiança
   ("A2–B1") é o `CefrAssessment` estimado, que é o CARD-046. Confundir os dois
   tipos no domínio faria a apresentação mentir sobre a origem do dado.
3. `GET`/`PATCH` do perfil do aluno para ler e mudar o nível — e **mudar tem de
   ser possível a qualquer momento**, não só no onboarding: o aluno que se
   subestimou precisa poder corrigir sem recriar a conta.
4. A tela do app: uma pergunta simples de autoavaliação, com descrições em
   português do que cada nível significa em termos de conversa (não a
   nomenclatura CEFR crua, que não diz nada a quem não a conhece).
5. O bloco de contexto passa a instruir o professor a calibrar **vocabulário,
   velocidade e tolerância a erro** — e a **não anunciar o nível** (ADR-0059
   item 3). Um professor que diz "como você é A2, vou falar devagar" transforma
   uma escolha do aluno em rótulo.

## Refinamento obrigatório — cache e limites

**Cache:** o nível é lido a cada turn para montar o contexto. **Não cachear
ainda**: é uma leitura por id na mesma transação que já busca o aluno, e o
projeto não cacheia o que não mediu. Se virar problema, TTL seria a sessão e a
invalidação o `PATCH` do perfil — as duas respostas existem, o que falta é o
problema.

**Endpoint:** `GET`/`PATCH /v1/students/me` (ou equivalente na convenção
existente). **Teto:** por conta, baixo no `PATCH` — mudar de nível é ação rara.
Proposta declarada: **10/min**, camada de aplicação. **Autorização:** o aluno só
lê e muda a si mesmo; nunca aceitar `student_id` do corpo.

**Dependência externa:** não se aplica no servidor. No cliente, o `PATCH` passa
pela mesma política do CARD-026 e do client do ADR-0046. Idempotente: sim,
`PATCH` do mesmo nível é no-op. Desfecho quando o servidor está fora: a tela
mostra o nível atual e diz que a mudança não foi salva — nunca finge sucesso.

## Escopo

- **In:** `CefrLevel` no domínio; `cefr_level` em `Student` + migration;
  leitura/escrita do perfil; a tela de autoavaliação; o nível no
  `StudentContext` e no bloco de contexto; a instrução de calibragem no prompt.
- **Out:** estimar o nível (CARD-046). Mini-teste (CARD-047). Mostrar o nível em
  tela de progresso — a tela prevista na visão é da web companion e tem card
  próprio. Reavaliação automática.

## Critérios de aceite

- **Dado** um aluno sem nível declarado, **quando** um turn é processado,
  **então** o prompt é **idêntico** ao de hoje — nenhuma regressão para quem não
  declarou.
- **Dado** um aluno com `A2`, **quando** o prompt é montado, **então** o bloco
  de contexto contém o nível, no final do prompt de sistema, e `v2.md` continua
  sendo o prefixo byte-a-byte.
- **Dado** um aluno com nível declarado, **quando** a resposta do professor é
  lida, **então** ela **não menciona o nível** ao aluno — verificável no prompt
  por teste de conteúdo; verificável na saída só por conversa real, e isso está
  escrito como limitação.
- **Dado** o aluno na tela de perfil, **quando** muda o nível, **então** o turn
  seguinte já usa o novo — sem reiniciar o app.
- **Dado** um `PATCH` com nível inválido, **quando** processado, **então**
  Problem Details (ADR-0040), não `500`.
- **Dado** um `PATCH` com `student_id` de outra conta no corpo, **quando**
  processado, **então** ele é ignorado — o dono vem do token, sempre.

## Riscos

- **Nível errado piora a conversa em silêncio.** O aluno que se subestima recebe
  um professor fácil demais e ninguém percebe pelo log. É o risco central do
  ponto 5 inteiro (ADR-0059) e a razão de o CARD-046 existir — a estimativa por
  desempenho é a correção do autodeclarado, não um enfeite.
- **Autoavaliação é notoriamente ruim.** A mitigação de produto é a redação da
  pergunta: perguntar o que a pessoa **consegue fazer** ("consigo manter uma
  conversa simples sobre o meu dia") em vez de pedir um rótulo.
- **Migration numa tabela viva.** Coluna nula é aditiva e segura; o cuidado é a
  ordem entre migration e deploy do código que a lê.

## Objetivo de aprendizado

Entender **enum de domínio em Python** (`enum.StrEnum`) e por que ele não é o
`enum` de C#: aqui o valor é o próprio texto persistido, não um inteiro
implícito, e a consequência prática é que **renomear um membro quebra dados**
enquanto reordenar não quebra nada — o inverso exato da armadilha do C#, onde
reordenar é que corrompe. Onde a conversão para o banco acontece (e por que
`StrEnum` a torna quase invisível no SQLAlchemy) é a parte que transfere.

## Execução (2026-09-13, loop autônomo) — BLOQUEADO, duas causas independentes

**Não implementado.** Duas dependências reais deste card não existem, e
nenhuma das duas é dado que eu deva inventar:

1. **O mecanismo do ADR-0059 (`StudentContext`, o bloco anexado ao prompt)
   nunca foi construído.** O CARD-041, que este card cita como pré-requisito
   ("o mecanismo é o do ADR-0059, criado pelo CARD-041"), ficou **bloqueado**
   nesta mesma sessão por um conflito de produto não resolvido (ver a
   "Execução" do CARD-041) — a peça que este card diz só precisar "acrescentar
   um campo" a ela simplesmente não existe ainda.
2. **`GET`/`PATCH /v1/students/me` não tem como ser implementado hoje.** O
   próprio nome da rota (`me`) pressupõe identidade do chamador, e este
   backend **não tem nenhuma autenticação** (achado já registrado na
   "Execução" do CARD-043, mesma sessão) — não é lacuna nova, é o mesmo
   CARD-049 ainda em backlog. Diferente do "só o dono cancela" do CARD-043
   (onde a autorização era um reforço sobre um endpoint já definível sem
   ela), aqui a rota **não tem definição** sem saber quem é "eu": não há
   `student_id` a aceitar do corpo (a regra de aceite proíbe isso
   explicitamente) nem sessão para resolvê-lo sozinho.

**Efeito em cascata, registrado para quem retomar:** o CARD-046 já está
marcado no backlog como "quebrar antes de começar" (ADR pendente, sem
evidência) e depende deste card; o CARD-047 já está marcado "mapeado, sem
data" por decisão do próprio desenvolvedor. Nenhum dos dois precisou de nota
nova — já refletem corretamente que não são para agora.

**O que destrava isto:** o CARD-041 resolvido (nas duas alternativas
possíveis, ver o card) destrava o item 5 da proposta técnica (nível no
`StudentContext`); o CARD-049 (autenticação) destrava o `GET`/`PATCH`. Sem os
dois, este card não tem por onde começar de verdade — não é um caso de
"comece pela parte que dá".

**Com isto, a lista de cinco pontos do loop (041 → 044 → 043 → 045 → 046 →
047) chega ao fim desta sessão.** Nenhum dos seis foi implementado — cada um
foi bloqueado ou adiado por um motivo registrado e verificável (conflito com
o CARD-040, escuta humana pendente, escopo/risco do próprio ADR-0058, ou
dependência não construída), nunca por adivinhação. O único item da lista de
prioridade que saiu implementado nesta sessão foi o CARD-057, que veio antes
por ser urgente e destravar o CI.
