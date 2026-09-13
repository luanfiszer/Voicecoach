# CARD-060 — Login social: Google e Sign in with Apple, os dois juntos

- **ID:** CARD-060
- **Épico:** Contas e auth de verdade (bloqueante de V1.0 se o app for publicado
  oferecendo login de terceiro)
- **Esforço:** M
- **Status:** backlog
- **Dependências:** CARD-049 (a base de e-mail+senha, JWT e refresh precisa
  existir primeiro), **ADR novo** (revisa o ADR-0007, que hoje diz "sem login
  social no MVP")

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
