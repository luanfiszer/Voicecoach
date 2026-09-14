# CARD-060 — Login social: Google e Sign in with Apple, os dois juntos

- **ID:** CARD-060
- **Épico:** Contas e auth de verdade (bloqueante de V1.0 se o app for publicado
  oferecendo login de terceiro)
- **Esforço:** M
- **Status:** bloqueado (2026-09-13) — ver "Execução"
- **Dependências:** CARD-049 (a base de e-mail+senha, JWT e refresh precisa
  existir primeiro), [ADR-0070](../adr/0070-login-social-google-e-apple-juntos-vinculo-por-email.md)
  (revisa o ADR-0007, que dizia "sem login social no MVP")

## Contexto

Nasceu de uma pergunta do desenvolvedor durante a execução do CARD-049
(2026-09-13): *"quero autenticação com Google além da padrão"*.

**O ADR-0007 já respondeu por que isso não entra junto**, com o gatilho
escrito: *"publicação na App Store oferecendo qualquer login de terceiro
obriga Sign in with Apple"* (Guideline 4.8 da Apple — oferecer um provedor de
terceiro exige oferecer um equivalente da própria plataforma). **Não existe
"só Google" para um app iOS público** — a decisão de produto de fato é
"Google + Apple, os dois", não "Google".

Isso muda a forma do card: não é uma integração OAuth, são duas, com fluxos
de token diferentes (Google: `id_token` verificado contra a chave pública do
Google; Apple: `identityToken` JWT assinado pela Apple, com a peculiaridade de
o nome só vir na **primeira** autorização).

## Problema

Hoje o cadastro é só e-mail+senha (CARD-049). Login social reduz atrito de
cadastro — mas fazer só a metade (Google sem Apple) troca um problema de
produto por um problema de compliance na revisão da App Store.

## Proposta técnica

1. **Um port `SocialIdentityProvider`** (ou dois adapters atrás da mesma
   forma), verificando o token do provedor e devolvendo `(email, external_id,
   provider)` — nunca confiando em nada que o cliente afirme sem verificação
   criptográfica contra a chave pública do provedor.
2. **Vínculo de conta por e-mail verificado pelo provedor**: se o e-mail já
   existe (de um cadastro por senha), a conta social se **linka** à existente,
   não cria uma segunda. Precisa de decisão explícita: o que acontece se o
   e-mail do Google não é o mesmo already cadastrado por senha, ou se dois
   provedores sociais trazem e-mails diferentes para a mesma pessoa.
3. **Dependências novas**: uma biblioteca de verificação de JWT/JWKS para os
   dois provedores (ex.: reusar `PyJWT` com `PyJWKClient` para as duas chaves
   públicas, evitando SDK completo de cada provedor) — candidato a favorecer
   no ADR, mas precisa de comparação real, não suposição.
4. **Client ID/secret dos dois provedores não existem no `.env` hoje** — este
   card não pode ser fechado sem eles. Se a sessão que o executar não tiver
   acesso a criar as credenciais (conta de desenvolvedor Google Cloud, conta
   Apple Developer — a mesma do CARD-053), o card documenta o bloqueio e para,
   como qualquer outro card desta faixa (CLAUDE.md, "onde o cuidado dobra").

## Refinamento obrigatório — cache e limites

**Cache:** não se aplica — a identidade social não é cacheada; o par de
tokens que sai no fim é o mesmo do CARD-049 (JWT curto + refresh rotativo).

**Endpoint:** `POST /v1/auth/google`, `POST /v1/auth/apple` (ou um endpoint
único com `provider` no corpo — decisão de implementação). Mesmo teto de
abuso do CARD-049 se aplica (limite por IP); a verificação criptográfica do
token do provedor já limita o "confiar em qualquer coisa" que um endpoint de
auth social convida.

**Dependência externa:** os dois provedores (Google, Apple), na verificação
do token — chamada às chaves públicas JWKS, cacheável pela própria biblioteca
(rotação de chave é rara). Timeout e retry seguem a política do CARD-026.
Desfecho quando o provedor de JWKS está fora: login falha com Problem
Details claro, nunca 500 mudo — o aluno tenta de novo ou usa e-mail/senha.

## Escopo

- **In:** os dois provedores juntos (não é opcional escolher um só, pela
  regra da App Store); o ADR que revisa o ADR-0007; vínculo com conta
  existente por e-mail.
- **Out:** qualquer outro provedor social (Facebook, etc. — nenhum gatilho
  para eles); mudar o fluxo de e-mail+senha do CARD-049.

## Critérios de aceite

- **Dado** um `id_token` do Google válido, **quando** postado no endpoint,
  **então** a conta é criada (ou linkada, se o e-mail já existe) e o par de
  tokens do CARD-049 é emitido.
- **Dado** um `identityToken` da Apple válido, **quando** postado no
  endpoint, **então** mesmo resultado — conta criada/linkada, par de tokens
  emitido.
- **Dado** um token de qualquer provedor **adulterado ou expirado**, **quando**
  postado, **então** a resposta é `401` com Problem Details, nunca 500.
- **Dado** um e-mail que já existe via cadastro por senha, **quando** o
  mesmo e-mail chega por um provedor social, **então** a conta é a mesma
  (linkada), não duplicada.

## Riscos

- **Nome do Apple só vem na primeira autorização** — se o backend não
  capturar nesse instante, não há segunda chance sem o usuário revogar o
  acesso ao app nas configurações da conta Apple. Vale um teste específico
  para isso.
- **Sem conta de desenvolvedor Google/Apple configurada ainda** — mesmo
  bloqueio que qualquer segredo real ausente do `.env` (CLAUDE.md).

## Objetivo de aprendizado

Verificação de identidade federada sem SDK completo do provedor — validar um
JWT assinado externamente contra um JWKS público (chave rotativa, cache de
chave pública) é um padrão que aparece em qualquer integração OAuth/OIDC, e
o equivalente .NET seria `Microsoft.IdentityModel.Protocols.OpenIdConnect`
fazendo o mesmo papel de buscar e cachear o JWKS.

## Execução (2026-09-13, loop autônomo) — backend completo, bloqueado no resto

### O que foi implementado e testado

- **[ADR-0070](../adr/0070-login-social-google-e-apple-juntos-vinculo-por-email.md)**
  — a decisão de vínculo, os dois adapters (`PyJWT`+`PyJWKClient`, não SDK
  completo), a `Credential` sem senha para conta puramente social, e o
  `display_name_hint` da Apple. Lida antes de escrever qualquer código.
- **Domínio**: `SocialProvider` (enum fechado, Google/Apple) e
  `SocialIdentity` (`domain/auth.py`) — entidade própria, nunca coluna em
  `Credential`, porque uma pessoa pode ter os dois provedores ao mesmo
  tempo.
- **Porta `SocialIdentityProvider`** (`application/ports/social_identity.py`)
  e **`SocialIdentityRepository`** (`application/ports/auth_repositories.py`).
- **`LoginWithSocialHandler`** (`application/use_cases/login_with_social.py`):
  a regra de vínculo completa — reconhece pelo `(provider, external_id)`,
  linka por e-mail numa `Credential` existente, ou cria os três (Student +
  Credential + SocialIdentity) na primeira vez. Testado com um
  `SocialIdentityProvider` fake — a verificação criptográfica é testada nos
  adapters.
- **`GoogleIdentityProvider`/`AppleIdentityProvider`**
  (`adapters/auth/`) — verificação RS256 via `PyJWKClient`, com executor
  (mesma razão do `boto3`/ADR-0034: a busca da chave é síncrona). Testados
  com um par de chaves RSA gerado na hora e um `_ClienteDeChaves` fake — sem
  bater no Google/Apple de verdade. Cobrem: token válido, assinado com outra
  chave, audiência errada, emissor errado, expirado, sem e-mail, JWKS fora
  do ar, e — específico da Apple — `email_verified` chegando como STRING
  (`"true"`/`"false"`, documentado pela Apple, não bug do PyJWT).
- **`social_identities`** (migration `a4d8f2c19e6b`, testada com
  `alembic upgrade head`/`downgrade -1` contra Postgres real): tabela nova,
  `(provider, external_id)` único, `ON DELETE CASCADE` para `students.id`
  (ao contrário do `usage_events` do ADR-0069, aqui não há nada a
  anonimizar).
- **`POST /v1/auth/google`, `POST /v1/auth/apple`** — dois endpoints (não um
  unificado, decisão registrada no ADR), rate limit por IP, `503` (não
  `500`, nunca silêncio) quando `GOOGLE_CLIENT_ID`/`APPLE_CLIENT_ID` não
  estão configurados.
- **`Cliente.loginGoogle`/`loginApple`** em `packages/api-client` — os dois
  métodos HTTP, testados com `fetch` fake. **Sem tela nem SDK nativo** — ver
  "O que ficou bloqueado".

### O que ficou bloqueado, e por quê (o próprio card previa isto)

- **Sem `GOOGLE_CLIENT_ID` nem `APPLE_CLIENT_ID` (Services ID) reais.** Os
  dois exigem uma conta Google Cloud e um Apple Developer Program
  (pago, matrícula em nome do desenvolvedor) — fora do alcance desta sessão,
  exatamente como o próprio card previa ("se a sessão não tiver acesso... o
  card documenta o bloqueio e para"). Nada foi verificado contra os
  provedores de verdade; só contra chaves RSA de teste.
- **Nenhuma UI de sign-in no app mobile.** Botões nativos de Google/Apple
  exigem os SDKs nativos (`@react-native-google-signin/google-signin`,
  `expo-apple-authentication`) instalados e configurados com as MESMAS
  credenciais reais que faltam — construir a tela sem elas produziria
  código que não roda e não pode ser testado nem no Simulador. `apps/mobile`
  não foi tocado neste card.
- **`enforce_social_login_rate_limit`/os dois endpoints nunca foram
  exercitados contra o Google ou a Apple reais** — só via fakes/testcontainers.

### Decisões técnicas registradas (não perguntas ao vivo)

Todas decorrem direto do texto do próprio card ou de ADRs já existentes
(ADR-0007, ADR-0051) — nenhuma cruzou o limiar de "decisão de produto que só
o desenvolvedor pode tomar":

- Dois endpoints, não um unificado (corpos diferentes entre os provedores).
- `PyJWT`+`PyJWKClient` em vez de SDK completo (o card já pedia "comparação
  real, não suposição" — a comparação é a ausência de SDK oficial da Apple).
- `Credential` sem senha para conta puramente social, reaproveitando toda a
  máquina de verificação de e-mail do CARD-049 sem mudar uma linha dela.
- `GOOGLE_CLIENT_ID`/`APPLE_CLIENT_ID` como configuração opcional (são
  públicos, não segredo) em vez de fail-fast no boot — o oposto do
  `jwt_secret`, e a razão está no ADR.

### Gates

Backend: `ruff format/check`, `mypy --strict`, `lint-imports` verdes;
`pytest --cov` verde (653 testes; a suíte completa do projeto, não só deste
card). Cliente: `pnpm run gates` verde, 86 testes.

### Como retomar

Quando o desenvolvedor tiver as duas credenciais: (1) configurar
`GOOGLE_CLIENT_ID`/`APPLE_CLIENT_ID` no `.env`; (2) testar os dois endpoints
com um token real de cada provedor (o backend já está pronto para isso, sem
mudança de código); (3) instalar os SDKs nativos no `apps/mobile` e
construir as duas telas/botões, chamando `Cliente.loginGoogle`/`loginApple`
já prontos. Cada uma das três etapas é independente — não precisam ser
feitas na mesma sessão.
