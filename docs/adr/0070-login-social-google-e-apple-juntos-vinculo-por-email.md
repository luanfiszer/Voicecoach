# ADR-0070 — Login social: Google e Apple juntos, vínculo por e-mail verificado

- **Status:** aceito · **revisa** o item "Sem login social no MVP" do [ADR-0007](0007-autenticacao-jwt-refresh-rotativo.md) — o gatilho que aquele ADR escreveu ("publicação oferecendo login de terceiro obriga Sign in with Apple") chegou
- **Data:** 2026-09-13
- **Relacionado:** ADR-0007 (JWT + refresh rotativo), CARD-049, CARD-060
- **Critérios de obrigatoriedade:** **1 — nova dependência externa** (`pyjwt[crypto]`, que traz `cryptography`), **2 — nova fronteira** (dois endpoints, um esquema de vínculo de identidade que não existia) e **4 — privacidade** (verificação de identidade de terceiro, dados de outro provedor entrando na conta).

## Contexto

Nasceu de uma pergunta do desenvolvedor durante o CARD-049 (2026-09-13):
*"quero autenticação com Google além da padrão"*. O ADR-0007 já respondia por
que isso não entraria junto: publicar um app iOS oferecendo qualquer login de
terceiro obriga a oferecer Sign in with Apple (Guideline 4.8 da Apple) — não
existe "só Google" para este produto. A decisão de produto de fato é "Google
e Apple, juntos", e foi por isso que a pergunta virou o CARD-060 em vez de
uma linha a mais no CARD-049.

Isso muda a forma do problema: não é uma integração OAuth, são duas, com
formatos de token diferentes (Google: `id_token`, com `name` dentro do JWT
quando o escopo `profile` foi pedido; Apple: `identityToken`, que **nunca**
carrega nome — a Apple entrega o nome só na primeira autorização, fora do
JWT, e só para o cliente).

**O bloqueio real, dito sem rodeio:** este ADR e o código que o acompanha
foram escritos sem `GOOGLE_CLIENT_ID` nem `APPLE_CLIENT_ID` (o Services ID da
Apple) reais — a sessão que executou o CARD-060 não tinha acesso para criar
uma conta Google Cloud nem um Apple Developer Program. O card já previa este
exato desfecho como aceitável ("se a sessão não tiver acesso... o card
documenta o bloqueio e para").

## Decisão

**Verificar o JWT de cada provedor com `PyJWT` + `PyJWKClient` contra o JWKS
público dele (nunca o SDK completo); vincular por e-mail verificado a uma
conta existente em vez de duplicar; e tratar a identidade social como
entidade própria, nunca como coluna em `Credential`.**

1. **Os dois provedores entram juntos, e nenhum deles é opcional** — é a
   decisão de produto que o ADR-0007 já tinha antecipado, agora executada.
2. **`SocialIdentity(id, student_id, provider, external_id, email,
   created_at)`, entidade própria** (`domain/auth.py`), com
   `(provider, external_id)` único. Não é coluna em `Credential` porque uma
   pessoa pode ter Google **e** Apple ao mesmo tempo — duas linhas, um
   `student_id` só. `external_id` (o `sub` do token), nunca o e-mail, é a
   chave de identidade PARA aquele provedor — o próprio card nomeia o risco
   de dois provedores devolverem e-mails diferentes para a mesma pessoa, e
   usar e-mail como chave escondería exatamente esse caso.
3. **A regra de vínculo, em ordem:** `(provider, external_id)` já visto ⇒
   mesma conta de sempre. Senão, `email` já existe numa `Credential` (a
   pessoa se cadastrou por senha antes) ⇒ linka: a `SocialIdentity` nova
   aponta para aquele `student_id`, nenhum `Student` novo. Senão, é a
   primeira vez ⇒ cria `Student` + `Credential` (sem senha usável) +
   `SocialIdentity`, os três juntos.
4. **Conta puramente social recebe uma `Credential` com um hash argon2id
   inválido fixo** (o mesmo idioma do `_HASH_DE_PREENCHIMENTO` do
   `login_student.py`, com outro motivo: aqui não há senha nenhuma, e uma
   coluna nulável que todo outro código teria de checar custaria mais que um
   valor que nunca confere). Consequência deliberada: `enforce_verified_email`,
   "esqueci minha senha" e todo o resto do CARD-049 funcionam sobre uma conta
   social **sem mudar uma linha** — "esqueci minha senha" inclusive dá a um
   aluno social o caminho natural para adicionar uma senha, se quiser.
5. **`PyJWT` + `PyJWKClient`, não os SDKs dos provedores.** `PyJWT` já é
   dependência (ADR-0007, HS256 do nosso próprio access token); o extra
   `[crypto]` só acrescenta `cryptography` para RS256. A Apple não publica
   SDK oficial em Python — seria código próprio de qualquer forma —, e isso
   é o que torna a simetria com o Google uma decisão e não um acidente: os
   dois adapters (`google_identity_provider.py`, `apple_identity_provider.py`)
   têm a mesma forma, buscando a chave via executor (mesma razão do
   `boto3`/ADR-0034: `PyJWKClient` é síncrono por dentro).
6. **`display_name_hint` no comando `LoginWithSocial`, só para a Apple.** O
   `identityToken` nunca carrega nome — o cliente precisa mandá-lo separado,
   capturado no instante único da primeira autorização (`display_name`, no
   corpo de `POST /v1/auth/apple`). Ignorado em qualquer chamada seguinte,
   porque a conta já existe.
7. **`email_verified` e `is_private_email` da Apple chegam como STRING**
   (`"true"`/`"false"`), documentado pela própria Apple. `_claim_booleana`
   trata isso explicitamente — um `bool()` ingênuo leria `"false"` como
   verdadeiro, porque toda string não vazia é *truthy* em Python.
8. **`GOOGLE_CLIENT_ID`/`APPLE_CLIENT_ID` são configuração opcional, sem
   fail-fast no boot.** Os dois são valores **públicos** do provedor (vão no
   `app.json`/Info.plist do cliente, para o SDK nativo) — não são segredo, e
   por isso não recebem o tratamento de `jwt_secret`/`resend_api_key`. Sem
   eles, o processo sobe normalmente; a rota recusa com `503` ("provedor não
   configurado") se alguém chamar o endpoint antes de as credenciais reais
   existirem — nunca `500`, nunca silêncio.

## Alternativas consideradas

### Alternativa A — SDK completo de cada provedor (`google-auth` + equivalente)

- **O que é:** usar a biblioteca oficial do Google para verificar o
  `id_token`, e para a Apple montar a verificação à mão de qualquer forma
  (não há SDK oficial).
- **Por que foi rejeitada:** o SDK do Google traz cliente HTTP próprio e uma
  superfície bem maior do que "verificar um JWT contra uma chave pública" —
  exatamente o que `PyJWKClient` já resolve com uma dependência que o projeto
  já tinha. E como a Apple obrigaria código próprio de qualquer forma, usar
  SDK só do Google quebraria a simetria entre os dois adapters sem ganho
  real.

### Alternativa B — Coluna de provedor social em `Credential`

- **O que é:** acrescentar `social_provider`/`social_external_id` nulável à
  tabela `credentials`, em vez de uma tabela nova.
- **Por que foi rejeitada:** uma pessoa com Google **e** Apple precisaria de
  duas linhas em `credentials` para a MESMA conta — o que essa tabela nunca
  modelou (é "um aluno, uma credencial de senha"). Forçar isso quebraria a
  invariante `student_id` único de `CredentialRepository.get_by_student_id`.

### Alternativa C — Um endpoint único (`POST /v1/auth/social`, com `provider` no corpo)

- **O que é:** um só endpoint, discriminando por campo.
- **Por que foi rejeitada:** os dois provedores mandam corpos diferentes
  (`id_token` vs. `identity_token` + `display_name` opcional) — um corpo
  condicional (campos que só valem para um `provider`) é contrato pydantic
  pior do que dois schemas simples, e o Problem Details de cada rota fica
  mais claro apontando para o endpoint certo. O próprio card deixava a
  escolha aberta como "decisão de implementação".

## Consequências

**Positivas**

- Nenhuma conta duplicada quando a mesma pessoa usa e-mail+senha e depois
  login social (ou os dois provedores sociais) — o critério de aceite
  central do card.
- Reaproveita toda a máquina de auth do CARD-049 (verificação de e-mail,
  emissão de token, refresh, "esqueci minha senha") sem tocar uma linha
  dela — a `Credential` sem senha é o que torna isso possível.
- Simetria entre os dois adapters reduz a superfície nova a "duas vezes a
  mesma solução", não duas soluções diferentes.

**Negativas — o preço aceito**

- `cryptography` entra como dependência nova (via `pyjwt[crypto]`) — mais
  peso de build, e mais uma entrada nas listas `forbidden` do
  `lint-imports` (domain e application).
- **Nada foi verificado contra o Google ou a Apple de verdade** nesta
  sessão — só contra uma chave RSA de teste, gerada na hora. É o bloqueio
  que o próprio card previa, e ele continua até o desenvolvedor criar as
  duas credenciais.
- Login social paga duas consultas a mais que o login por senha
  (`get_by_provider` e, quando não encontra, `get_by_email`) — aceitável
  porque login não é o caminho quente do produto (turns são).
- Um aluno puramente social nunca teve senha — se esquecer que pode pedir
  "esqueci minha senha" para criar uma, fica sem alternativa de e-mail+senha
  até fazer isso. Não é um bug: é a consequência correta de "conta social
  não tem senha", só vale nomear.

**Equivalente mental .NET:** a verificação de JWKS é o mesmo papel de
`Microsoft.IdentityModel.Protocols.OpenIdConnect` com
`ConfigurationManager<OpenIdConnectConfiguration>` cacheando as chaves; o
vínculo por e-mail é o mesmo problema que o ASP.NET Identity resolve com
`UserManager.AddLoginAsync` sobre um `ExternalLoginInfo` — "encontrar o
usuário pelo e-mail do provedor externo e associar, em vez de criar de
novo" é a mesma operação, com nome diferente.
