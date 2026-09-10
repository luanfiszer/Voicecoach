# CARD-049 — Cadastro, login e o par de tokens: a auth que o ADR-0007 desenhou

- **ID:** CARD-049
- **Épico:** Contas e auth de verdade (bloqueante de V1.0 — N3 do corte)
- **Esforço:** M
- **Status:** backlog
- **Dependências:** ADR-0007, **ADR novo obrigatório** (provedor de e-mail)

## Contexto

Bloqueante do lançamento, identificado em
[`docs/corte-v1-o-que-bloqueia-o-lancamento.md`](../corte-v1-o-que-bloqueia-o-lancamento.md).
Até hoje isto era uma linha "a detalhar" no backlog — e cobrar dinheiro de gente
exige, antes de tudo, saber quem é quem.

**O desenho já existe e não precisa ser reaberto:** o ADR-0007 decidiu
e-mail+senha com argon2id, JWT de ~15 min, refresh opaco rotativo persistido
com detecção de reuso, e `expo-secure-store` no cliente. Este card **executa**
esse ADR na parte do servidor.

**O que mudou, e é o gatilho deste card:** o ADR-0010 item 5 substituiu, no MVP,
a verificação de e-mail por um **código de convite**, com o gatilho escrito de
volta para o "beta aberto". **App Store pública é o beta aberto** — o convite
morre e a verificação de e-mail do ADR-0007 original volta.

**Débito de negócio.** Nada está errado no código; a regra mudou de fase.

## Problema

Não há conta. A API identifica o aluno por `student_id` sem que ninguém prove
ser ele; a proteção é allowlist/convite por configuração. Isso não sobrevive a
um app que qualquer pessoa baixa — e sem conta não há assinatura, não há cota
por aluno e não há delete de conta (CARD-051, exigência da Apple).

## Proposta técnica

1. **Hash de senha com `argon2-cffi`** (argon2id), parâmetros explícitos e
   comentados. Nunca bcrypt "porque é o que todo mundo usa": o ADR já escolheu.
2. **Access token JWT com `PyJWT`**, ~15 min, carregando `student_id`, validado
   *stateless* na borda. O trade-off já está aceito no ADR-0007: **até 15 min de
   token válido depois de revogado**.
3. **Refresh opaco, rotativo, persistido em hash**, ~30 dias. Cada refresh emite
   par novo e invalida o anterior; **reuso de um refresh antigo revoga a família
   inteira** — é a detecção de roubo, e é o pedaço que mais vale como
   aprendizado.
4. **Verificação de e-mail obrigatória antes do primeiro turn** (ADR-0007), não
   antes do login. Deixar entrar e barrar no turn é o que evita que uma falha de
   entregabilidade de e-mail vire uma tela morta no primeiro minuto de uso.
5. **Um provedor de e-mail transacional entra no projeto**, e isso é
   **ADR obrigatório** — critério **1** do `adr/README.md` (introduz dependência
   externa) e critério **3** (o ADR-0010 evitou essa dependência de propósito;
   ele deixa de valer). O ADR precisa escolher o provedor, dizer o custo e
   definir o desfecho quando o e-mail não sai.
6. A borda ganha a dependência de aluno autenticado, e **`student_id` deixa de
   vir de qualquer lugar que não seja o token** — em nenhuma rota, nunca do
   corpo.

## Refinamento obrigatório — cache e limites

**Cache:** o JWT **é** o cache da identidade — é essa a escolha do ADR-0007
contra sessão server-side. TTL: 15 min, e é o número que define a janela de
revogação. Invalidação: não há, por desenho; o que se invalida é o refresh, no
banco. Isto precisa estar escrito no código, não só no ADR.

**Endpoint:** `POST /v1/auth/register`, `/login`, `/refresh`, `/logout` e a
confirmação de e-mail. **Teto, e ele é a linha de frente do abuso:** login por
IP **e** por e-mail (o segundo é o que impede varredura de senha numa conta
alvo); registro por IP. Proposta declarada: **10/min por IP no login, 5/min por
e-mail, 3/h por IP no registro** — estimativas, recalibradas por métrica. A
proteção mais completa do cadastro é o **CARD-054**.

**Dependência externa:** o provedor de e-mail. **Timeout:** teto explícito, com
a política do CARD-026 — nunca requisição crua. **Idempotente:** reenviar a
confirmação é seguro e deve ser possível; o link em si é de uso único.
**Desfecho quando o provedor está fora:** o cadastro **conclui** e o e-mail é
retentado — falhar o cadastro porque um terceiro caiu perde o usuário para
sempre. O aluno vê "confirme seu e-mail" e um botão de reenviar.

## Escopo

- **In:** entidade e migration de credencial e de refresh token; argon2id; os
  endpoints; a dependência de aluno autenticado na borda; o ADR e a integração
  do provedor de e-mail; a verificação barrando o primeiro turn; os limites.
- **Out:** o cliente (CARD-050). Delete de conta (CARD-051). Login social —
  continua fora, e o ADR-0007 registra o gatilho: oferecer **qualquer** login de
  terceiro na App Store obriga Sign in with Apple. Recuperação de senha **entra
  aqui ou vira card próprio na execução** — ela é obrigatória para um app
  público, e é a primeira coisa a verificar no refinamento.

## Critérios de aceite

- **Dado** um e-mail já cadastrado, **quando** alguém tenta registrar de novo,
  **então** a resposta é a mesma de um cadastro novo — **não vazar quais e-mails
  existem** é requisito, não capricho.
- **Dado** um refresh token válido, **quando** usado, **então** vem um par novo e
  o antigo deixa de funcionar.
- **Dado** um refresh token **já rotacionado**, **quando** apresentado de novo,
  **então** a família inteira é revogada e todo access dela morre no vencimento.
  É o teste que prova o item 3, e ele é o coração do card.
- **Dado** um aluno com e-mail não verificado, **quando** posta um turn,
  **então** recebe Problem Details (ADR-0040) dizendo o que falta — não `403`
  mudo.
- **Dado** o provedor de e-mail fora, **quando** alguém se cadastra, **então** a
  conta existe e o reenvio funciona depois.
- **Dado** qualquer rota autenticada, **quando** recebe `student_id` no corpo,
  **então** ele é ignorado. O dono vem do token, sempre.
- **Dado** uma senha correta e uma incorreta, **quando** medidas, **então** o
  tempo de resposta não as distingue de forma útil.

## Riscos

- **Auth escrita à mão é risco assumido**, e o ADR-0007 o declarou aceitando o
  valor didático. O gatilho para reavaliar que ele escreveu — *"produto real com
  usuários reais, onde a responsabilidade de segurança supera o valor
  didático"* — **está sendo disparado por este lançamento**. Vale reler o ADR
  antes de começar e decidir conscientemente se ele continua valendo. Se não
  continuar, é ADR novo, não improviso.
- **Entregabilidade de e-mail sem domínio nem reputação** é problema real. Plano
  B: provedor com free tier decente e domínio próprio configurado (SPF/DKIM),
  o que provavelmente vira item do ADR.
- **Recuperação de senha esquecida no escopo** é o furo clássico. Está escrito
  no "Out" justamente para não ser esquecido.

## Objetivo de aprendizado

Entender **por que o refresh rotativo com detecção de reuso é o que torna JWT
revogável na prática** — e a assimetria que ele cria: o access é stateless e
irrevogável por 15 min, o refresh é stateful e revogável na hora. Em .NET o
ASP.NET Identity entregaria isso pronto; escrever a rotação à mão é ver onde a
família de tokens mora, o que "reuso" significa em concorrência, e por que o
`argon2id` tem parâmetros que **precisam** ser decididos e não herdados.
