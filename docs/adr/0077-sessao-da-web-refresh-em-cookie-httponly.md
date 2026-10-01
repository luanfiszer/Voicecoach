# ADR-0077 — Sessão da web: refresh em cookie HttpOnly, rotação atômica e uma aba por vez

- **Status:** aceito
- **Data:** 2026-10-01
- **Relacionado:** ADR-0007 (JWT + refresh rotativo), ADR-0008 (contrato aditivo), ADR-0040 (Problem Details), ADR-0070/0071 (Google), CARD-049, CARD-050, CARD-064
- **Critérios de obrigatoriedade:** **4 — segurança** (onde o navegador guarda a sessão; correção de uma corrida que contornava a detecção de reuso) e **2 — contrato** (rotas novas `/v1/auth/web/*`).

## Contexto

O ADR-0007 decidiu o par JWT curto + refresh rotativo com detecção de reuso,
e o mobile guarda o refresh no Keychain/Keystore. O navegador não tem cofre
equivalente. O desenvolvedor escolheu (sessão de 2026-10-01) **cookie
HttpOnly** em vez de `localStorage` ou só memória.

Ao preparar o desenho, a pergunta de previsão "duas abas renovam ao mesmo
tempo — o que acontece?" foi rodada com dois `curl` em paralelo contra o
backend, e expôs um defeito do CARD-049: as **duas** requisições recebiam
token novo. O handler lia o elo, conferia `revoked_at` e só depois o marcava
(*check-then-act*): a família bifurcava, e quem usasse um refresh roubado no
mesmo instante que o dono escapava da detecção de reuso.

## Decisão

1. **Rotação atômica:** `RefreshTokenRepository.try_revoke` é um `UPDATE …
   WHERE revoked_at IS NULL RETURNING id`; quem não recebe a linha perdeu a
   corrida e é tratado como **reuso** (família revogada). Medido depois: uma
   requisição ganha, a outra leva 401, e o token novo da vencedora também
   morre — a semântica do ADR-0007 sem brecha.
2. **Rotas `/v1/auth/web/{login,google,refresh,logout}`**, irmãs das do
   mobile, com os MESMOS casos de uso. Devolvem só o access token
   (`AccessTokenResponse`); o refresh vai num cookie `voicecoach_refresh`
   com `HttpOnly`, `Secure` (configurável para dev: `WEB_REFRESH_COOKIE_SECURE`),
   `SameSite=Strict`, `Path=/v1/auth/web` e `Max-Age` = TTL do refresh.
3. **Mesma origem, sem CORS:** a web fala com a API pelo proxy do Vite em
   desenvolvimento e por um reverse proxy no mesmo domínio em produção
   (CARD-055). Cookie `SameSite=Strict` + mesma origem é a defesa de CSRF.
4. **No cliente, uma aba renova por vez:** a renovação roda dentro de
   `navigator.locks.request('voicecoach-refresh', …)` (Web Locks API). A aba
   que espera, ao entrar, manda o cookie **já rotacionado** pela primeira —
   o navegador compartilha o cookie entre abas. Sem isso, duas abas
   deslogariam o aluno a cada expiração simultânea (item 1).
5. **Google na web aceita uma segunda audiência:** `GOOGLE_WEB_CLIENT_ID`,
   além do `GOOGLE_CLIENT_ID` do iOS; o adapter recebe a lista.

## Alternativas consideradas

### A — `localStorage` (como o mobile, sem mudar o backend)
- **Por que foi rejeitada:** qualquer XSS lê e exfiltra o refresh de 30 dias.
  Escolha do desenvolvedor.

### B — Só memória
- **Por que foi rejeitada:** recarregar a página desloga.

### C — Um "modo cookie" nas rotas existentes (header ou parâmetro)
- **Por que foi rejeitada:** `TokenPairResponse.refresh_token` teria de virar
  opcional, quebrando o tipo gerado do mobile (ADR-0008). Rotas irmãs são
  aditivas.

### D — CORS com `credentials: 'include'`
- **Por que foi rejeitada:** exige `SameSite=None` (o cookie passa a viajar
  em requisições de terceiros) e uma política de origens para manter. Mesma
  origem é mais simples e mais segura.

### E — Serializar entre abas com `BroadcastChannel` ou `localStorage` como trava
- **Por que foi rejeitada:** reimplementa um mutex com mensagens; a Web Locks
  API é a primitiva do próprio navegador (suportada nos navegadores atuais).

## Consequências

- Refresh que falha **não apaga** o cookie (a resposta de erro é montada pelo
  handler de Problem Details, que não carrega `Set-Cookie`). O cookie fica
  inerte até o próximo login ou logout. Aceito.
- O deploy (CARD-055) precisa servir web e API na mesma origem.
- A correção da corrida vale também para o mobile: ela estava no caso de uso.
