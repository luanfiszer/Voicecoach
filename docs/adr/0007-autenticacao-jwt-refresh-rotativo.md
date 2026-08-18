# ADR-0007 — Autenticação: e-mail+senha verificado, JWT curto + refresh rotativo em secure storage

- **Status:** aceito
- **Data:** 2026-08-17

## Contexto

O canal WhatsApp dava identidade de graça (número de telefone) e a allowlist
era a proteção de custo. Com app próprio e cadastro aberto, autenticação vira
nossa responsabilidade e é a primeira camada da proteção de custo
(diagnóstico §7.3). Contexto mobile: token guardado no device, sessões longas
(usuário não redigita senha), possibilidade de revogação.

## Decisão

- **Cadastro e-mail + senha** com **verificação de e-mail obrigatória antes do
  primeiro Turn** (parte da defesa de custo). Hash de senha com **argon2id**
  (`argon2-cffi`).
- **Access token JWT** de vida curta (~15 min), assinado no backend (`PyJWT`),
  carregando `student_id` — validado stateless nas rotas.
- **Refresh token opaco, rotativo, persistido no banco** (hash), vida ~30
  dias: cada refresh emite par novo e invalida o anterior; **reuso de refresh
  antigo revoga a família inteira** (detecção de roubo). Logout/troca de
  senha revogam.
- No app: tokens em **`expo-secure-store`** (Keychain/Keystore). Nunca
  AsyncStorage.
- **Sem login social no MVP.** Gatilho documentado: publicação na App Store
  oferecendo qualquer login de terceiro obriga Sign in with Apple (regra da
  loja).

## Alternativas consideradas

### Alternativa A — Provedor de identidade gerenciado (Auth0/Clerk/Supabase Auth/Firebase)
- O que é: terceirizar cadastro, login, verificação, refresh.
- Por que foi rejeitada: o objetivo declarado é aprendizado — auth de API é
  conteúdo central de entrevista backend e vira caixa-preta no provedor;
  free tiers mudam de regra; e o fluxo (verificação, rotação, revogação) é
  pequeno o bastante para ser construído com qualidade aqui. Gatilho para
  reavaliar: produto real com usuários reais, onde a responsabilidade de
  segurança supera o valor didático.

### Alternativa B — Sessão server-side com cookie/token opaco em todas as rotas
- O que é: sem JWT; toda request consulta a sessão no banco/Redis.
- Por que foi rejeitada: perde-se o aprendizado do par stateless/stateful e
  uma ida ao Redis por request para o caso comum. A revogabilidade que o
  token opaco daria está preservada onde importa (refresh no banco); o JWT de
  15 min limita a janela de um access token vazado. Trade-off explícito:
  aceitamos até 15 min de token válido pós-revogação.

### Alternativa C — Magic link / passwordless por e-mail
- O que é: login por link enviado ao e-mail, sem senha.
- Por que foi rejeitada: depende de entregabilidade de e-mail no caminho
  crítico de login (num projeto sem domínio/reputação de envio), e UX de
  mobile com deep link adiciona complexidade cedo. A verificação de e-mail do
  cadastro já usa o mesmo mecanismo uma única vez, onde falha é tolerável.

## Consequências

**Positivas**: currículo completo de auth de API (hash moderno, JWT, rotação,
detecção de reuso, secure storage mobile); revogação real; base pronta para
quotas por conta.

**Negativas — o preço aceito**: somos donos do risco de implementação de auth
(mitigado por testes dedicados e revisão); envio de e-mail vira dependência
(um provider transacional no free tier); access token vale até 15 min após
revogação; sem social login, o cadastro tem mais atrito.

**Equivalente mental .NET:** ASP.NET Identity + JWT bearer — com a rotação de
refresh implementada à mão em vez de herdada do framework.
