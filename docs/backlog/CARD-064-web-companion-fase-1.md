# CARD-064 — Web companion, fase 1: conta, histórico, cota e configurações

- **ID:** CARD-064
- **Épico:** Web companion (Fase 6 do roadmap, antecipada a pedido do desenvolvedor)
- **Esforço:** G
- **Status:** concluído (2026-10-01) — com o login Google da web pendente do client ID (ver "Pendente")
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

### Parte 2 — o app web (2026-10-01)

- `apps/web`: Vite 7 + React 19.2.3 + React Router 8 + CSS Modules, tokens do
  mobile em `theme/tokens.css` — [ADR-0078](../adr/0078-a-web-vite-react-router-css-modules-sem-biblioteca-de-ui.md)
  (critérios **1** e **5**). `vite` 8 recusado: exigia exceção na política de
  idade mínima de release do pnpm e dois `vite` no repo.
- Telas: entrar, criar conta, confirme seu e-mail, confirmar e-mail (link),
  esqueci/redefinir senha, histórico, conta (cota do dia + sair + excluir),
  configurações, e o lugar da conversa (CARD-065).
- `sessaoWeb.ts` (núcleo sem React): access token só em memória, renovação
  dentro de `navigator.locks`. Teste das duas abas com servidor falso e pote
  de cookies compartilhado: **com a trava, as duas ficam logadas; sem ela, a
  família morre** (o contraexemplo também é teste).
- `packages/api-client`: `lerCota()`.

### QA no navegador real (Chromium headless via Playwright, fora do repo)

20 verificações, todas verdes: deslogado → `/entrar`; senha curta avisa;
cadastro → "confirme seu e-mail"; link confirma; senha errada avisa; login com
Enter; **cookie `voicecoach_refresh` com `HttpOnly`, `SameSite=Strict`,
`Path=/v1/auth/web`, e `document.cookie` sem ele**; recarregar mantém logado;
histórico com uma sessão real (turn processado pelo worker); **duas abas
abertas ao mesmo tempo continuam logadas, e uma terceira entra depois**; cota
do dia; tema escuro com o fundo `#121211`; celular sem rolagem lateral;
excluir conta volta a `/entrar` e a conta não entra mais; todo 401 visto é
refresh sem sessão ou login recusado; nenhum erro de app no console.

Dois achados do QA:

1. **No celular a aba "Configurações" ficava cortada** num scroll lateral
   invisível — corrigido (abas quebram linha), reconferido em 390 px.
2. Copiar o cookie para outro contexto do navegador fez o servidor ver
   **reuso** e revogar a família — comportamento correto (é o cenário do
   cookie roubado); o roteiro passou a emular tema/viewport na mesma aba.

### Pendente

- **Google na web**: código pronto (GIS + `/v1/auth/web/google` + segunda
  audiência), **sem verificação real** até o desenvolvedor criar o client ID
  Web e preencher `GOOGLE_WEB_CLIENT_ID` (raiz) e `VITE_GOOGLE_WEB_CLIENT_ID`
  (`apps/web/.env.local`). Sem ele o botão não aparece.
- Os links dos e-mails ainda apontam para a API (JSON). As rotas
  `/confirmar-email` e `/redefinir-senha?token=` da web já existem para
  recebê-los quando o link mudar — decisão de deploy (CARD-055).
- Rever uma sessão (turns e correções) no histórico: o backend não tem a
  leitura de uma sessão com os turns.
- Logout em uma aba só vale nas outras quando o access de 15 min expira
  (`BroadcastChannel` resolveria; sem gatilho ainda).

### Regra do explicador

1 pergunta nesta sessão, no ponto da decisão do cookie → **dispensada pelo
desenvolvedor**. A execução demonstrou a resposta e achou o defeito de
rotação (registrado em `docs/perguntas-em-aberto.md`).
