# CARD-064 — Web companion, fase 1: conta, histórico, cota e configurações

- **ID:** CARD-064
- **Épico:** Web companion (Fase 6 do roadmap, antecipada a pedido do desenvolvedor)
- **Esforço:** G
- **Status:** em andamento (2026-10-01)
- **Dependências:** ADR-0001, ADR-0002, ADR-0007, ADR-0008, [ADR-0077](../adr/0077-sessao-da-web-refresh-em-cookie-httponly.md); CARD-049/050/051/060; a fase 2 é o [CARD-065](CARD-065-web-conversa-por-audio.md)

## Contexto

Pedido do desenvolvedor (2026-10-01): *"criar a versão web usando o backend
que temos, com telas análogas e no mesmo estilo — futuramente terá
investimento em UX e UI"*.

### Premissas confirmadas com o desenvolvedor antes do plano

| Premissa | Resposta |
|---|---|
| Escopo | **tudo, em duas fases**: esta (conta, histórico, cota, configurações) e o CARD-065 (conversa por áudio no navegador) |
| Onde o navegador guarda a sessão | **cookie HttpOnly** (backend muda) |
| Login com Google na web | **agora** (o desenvolvedor cria o client ID Web) |
| Visual | **provisório**: mesmos tokens do mobile (paleta, Instrument Sans, tom), CSS puro com variáveis, sem biblioteca de componentes — o redesign futuro troca tokens e componentes sem reescrever estado |

## Escopo

- **In:** entrar (e-mail+senha e Google), criar conta, confirmar e-mail,
  esqueci/redefinir senha, histórico de sessões (com "áudio expirado"),
  cota do dia, configurações (versão, limites, sair, excluir conta);
  tema claro/escuro pelo sistema.
- **Out:** conversa por áudio (CARD-065); Apple na web (depende do CARD-053);
  gráficos de progresso (sem endpoint de agregação ainda).

## Critérios de aceite

- **Dado** um aluno com conta, **quando** entra na web, **então** vê o
  histórico e a cota — e recarregar a página **não** desloga.
- **Dado** duas abas abertas, **quando** o access expira nas duas, **então**
  o aluno **continua logado** nas duas (uma renova, a outra espera).
- **Dado** o JavaScript da página, **então** ele não tem acesso ao refresh
  token (não está em corpo nenhum nem em cookie legível).
- **Dado** o login com Google na web, **então** a conta é a mesma do iPhone
  (mesmo e-mail).

## Objetivo de aprendizado

React **web** de verdade (DOM, CSS, roteamento no navegador) contra o React
Native que o projeto já tem — e sessão de navegador: por que `HttpOnly` +
`SameSite` + mesma origem substituem o Keychain, e por que abas são
"dispositivos" concorrentes do mesmo cookie.

## Execução

### Parte 1 — backend (2026-10-01)

- **Pergunta do explicador** (ponto da decisão do cookie): *"duas abas
  renovam ao mesmo tempo — o que acontece?"* → **dispensada pelo
  desenvolvedor** ("ok, continue"). Rodada mesmo assim com dois `curl` em
  paralelo, e a execução achou um **defeito de segurança do CARD-049**: a
  rotação era *check-then-act*, e as duas requisições recebiam token novo
  (família bifurcada, detecção de reuso contornável). Corrigido com
  `try_revoke` atômico; teste de aplicação + teste com duas conexões
  concorrentes no Postgres. Depois da correção, o comportamento demonstrado:
  uma aba ganha, a outra é reuso, **as duas deslogam** — daí a Web Locks API
  no cliente.
- Rotas `/v1/auth/web/{login,google,refresh,logout}` com o refresh em cookie
  `HttpOnly; Secure; SameSite=Strict; Path=/v1/auth/web`; `AccessTokenResponse`
  sem refresh no corpo. 6 testes de rota (cookie, rotação, reuso, logout,
  Google, contrato do mobile intacto).
- `GOOGLE_WEB_CLIENT_ID`: o adapter do Google aceita as duas audiências.
- `packages/api-client`: `loginWeb`, `loginGoogleWeb`, `renovarSessaoWeb`,
  `sairDaWeb`, com testes.
- [ADR-0077](../adr/0077-sessao-da-web-refresh-em-cookie-httponly.md)
  (critérios **4** e **2**).

### Parte 2 — o app web

*(em andamento)*
