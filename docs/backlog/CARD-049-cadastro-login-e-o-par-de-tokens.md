# CARD-049 — Cadastro, login e o par de tokens: a auth que o ADR-0007 desenhou

- **ID:** CARD-049
- **Épico:** Contas e auth de verdade (bloqueante de V1.0 — N3 do corte)
- **Esforço:** M
- **Status:** concluído (2026-09-13)
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

## Execução (2026-09-13, loop autônomo)

**As duas perguntas de produto da sessão foram feitas ao vivo ao
desenvolvedor** (registro completo em `docs/perguntas-em-aberto.md`): (1)
ativar `requesting_student_id()` com JWT real em TODAS as rotas já
existentes agora, aceitando quebrar o app sem cliente até o CARD-050 — **sim,
ativar tudo**; (2) login social (Google) junto deste card ou separado —
**separado, virou CARD-060** (Google exigiria Sign in with Apple também,
Guideline 4.8 da Apple — não é "card menor").

### O que foi implementado

- **Domínio** (`domain/auth.py`): `Credential`, `RefreshToken`,
  `EmailVerificationToken`, `PasswordResetToken` — quatro dataclasses puras,
  sem SQLAlchemy nem pydantic.
- **Portas**: `PasswordHasher` (argon2id, métodos `async` por rodar em
  executor — CPU-bound de propósito), `AccessTokenIssuer` (JWT), `EmailSender`
  (dois métodos: confirmação e redefinição de senha), `CredentialRepository`,
  `RefreshTokenRepository`, `EmailVerificationTokenRepository`,
  `PasswordResetTokenRepository`.
- **Seis casos de uso**: `RegisterStudent`, `LoginStudent`, `RefreshTokens`
  (rotação + detecção de reuso), `LogoutStudent`, `ConfirmEmail` +
  `ResendConfirmation`, e — **fora do escopo original, adicionado nesta
  sessão** — `RequestPasswordReset` + `ResetPassword` (ver "Recuperação de
  senha" abaixo).
- **Adapters**: `Argon2PasswordHasher` (`run_in_executor`, parâmetros OWASP
  explícitos), `JwtAccessTokenIssuer` (HS256), `ConsoleEmailSender` (default
  de custo zero) e `ResendEmailSender` (`httpx` puro, sem SDK) — escolha
  registrada no **ADR-0068**.
- **Persistência**: 4 tabelas novas (`credentials`, `refresh_tokens`,
  `email_verification_tokens`, `password_reset_tokens`), migrations escritas
  à mão, repositórios SQLAlchemy testados contra Postgres real
  (testcontainers).
- **Borda**: 8 endpoints em `/v1/auth` (`register`, `login`, `refresh`,
  `logout`, `confirm-email`, `resend-confirmation`,
  `request-password-reset`, `reset-password`); `requesting_student_id()`
  reescrito para decodificar o `Bearer` (era `DEV_STUDENT_ID` fixo);
  `enforce_verified_email` novo, no `POST /turns`; rate limit por IP
  (registro, refresh de senha) e por IP+e-mail (login).
- **Rotas existentes migradas**: `criar_sessao` (POST /sessions) e `ler_cota`
  (GET /students/me/quota) passaram de `DEV_STUDENT_ID` para o token real.

### Recuperação de senha — não estava no escopo original, e foi adicionada

O card nomeia isto por escrito, na seção "Riscos": *"recuperação de senha
esquecida no escopo é o furo clássico"* e no "Out": *"entra aqui ou vira card
próprio na execução"*. Ao revisar o card **antes** de declarar a sessão
concluída, decidi que **não abrir um card novo para um requisito de
segurança básico já nomeado pelo próprio card** é a leitura mais conservadora
— abrir um card separado arriscaria essa dívida nunca ser paga (a mesma
lição que o histórico de cards deste projeto já registra várias vezes:
dívida sem card fica esquecida). Implementado com o mesmo padrão de
`EmailVerificationToken` (tabela própria — a posse do link autoriza coisas
diferentes) e **uma invariante que o ADR-0007 já exigia e eu só cumpri**:
trocar a senha revoga **todas** as sessões do aluno (`revoke_all_for_student`
em todas as famílias de refresh, não só a de quem pediu o reset) — testado
contra Postgres real e ponta a ponta pela rota.

### Bugs achados pelos próprios testes, corrigidos antes do merge

1. **`Argon2PasswordHasher.verify` não cobria `InvalidHashError`** — a
   exceção do argon2-cffi para hash malformado herda de `ValueError`, não de
   `VerificationError` (hierarquias distintas, verificado com
   `.__mro__`). Sem o segundo `except`, um hash gravado por engano em outro
   formato faria login **crashar** (500) em vez de recusar (senha errada).
   Achado pelo teste `test_hash_malformado_nao_propaga_e_devolve_false`.
2. **`mark_email_verified` pedia `credential_id`, mas todo chamador só tem
   `student_id`** (é o que `EmailVerificationToken` carrega) — `KeyError` no
   primeiro teste que exercitou o roundtrip completo. Corrigido trocando a
   porta para filtrar por `student_id` (único em `credentials`).
3. **A rota `confirm-email` reusava `TYPE_INVALID_REFRESH_TOKEN`** no erro
   400 em vez de um tipo próprio — copiado por descuido do endpoint de
   refresh vizinho. Corrigido com `TYPE_INVALID_EMAIL_CONFIRMATION_TOKEN`
   novo, achado ao revisar a rota antes de escrever o teste de API.

Nenhum dos três chegou a ser mergeado — todos foram achados e corrigidos
dentro desta mesma sessão, antes do PR.

### ADR e decisões técnicas

- **ADR-0068** (provedor de e-mail, critério 1+3+4 do
  `docs/adr/README.md`): Resend, com `ConsoleEmailSender` como default de
  custo zero. **Limitação registrada, não escondida**: sem domínio
  verificado, o sandbox do Resend só entrega para o e-mail da própria conta
  — o clique de confirmação de um aluno real não pode ser testado ponta a
  ponta até o CARD-055 (domínio). O mecanismo (geração/hash/expiração/
  revogação de token) está testado inteiramente sem depender disso.
- **PENDENTE DE REVISÃO HUMANA**: `RESEND_API_KEY` não existe no `.env`
  desta sessão (CLAUDE.md: não lidar com segredo real em modo autônomo) —
  `EMAIL_PROVIDER` fica em `console` até o desenvolvedor criar a conta
  Resend e decidir se/quando verificar um domínio.
- Alvo de tradução do login social ficou fora deste card por decisão do
  desenvolvedor (P2 acima) — CARD-060 criado.
- Nenhum outro ADR além do 0068: PyJWT/argon2-cffi já estavam decididos pelo
  ADR-0007 (só entraram no `pyproject.toml` e nas listas `forbidden`).

### Gates

`uv run ruff format/check`, `mypy`, `lint-imports` — verdes. `pytest --cov`:
94% global (gate 80%), **99% no núcleo `domain`+`application`** (gate 90%).
Suíte de auth: 11 testes de rota (incluindo os dois fluxos completos —
registro→confirmação→login→refresh com reuso→logout, e
esqueci-minha-senha→reset→sessões antigas mortas), 6 de persistência contra
Postgres real, ~35 de domínio/application/adapter.

### Pendências reais para quem revisar

- Conta Resend e `RESEND_API_KEY` (acima).
- `criar_turn`/`criar_sessao` agora exigem token real — **o app mobile
  quebra até o CARD-050** existir. Foi a decisão explícita da P1.
- Recuperação de senha não tem UI nenhuma ainda (o e-mail carrega o token
  como texto/query string, não um formulário) — trabalho de cliente,
  CARD-050/052.
