# apps/web — app web companion (Vite + React)

Fase 1 no ar (CARD-064): entrar (e-mail+senha e Google), criar conta,
confirmar e-mail, esqueci/redefinir senha, histórico, cota do dia, conta
(sair, excluir) e configurações. A conversa por áudio é o CARD-065.

## Rodar

```bash
# backend na porta 8000 (o alvo do proxy), da pasta backend/:
EMAIL_PROVIDER=console uv run uvicorn voicecoach.api.app:create_app --factory --port 8000
uv run voicecoach-worker            # para o histórico ter conversas novas

# a web, da raiz do repositório:
pnpm --filter @voicecoach/web dev   # http://localhost:5173
```

`EMAIL_PROVIDER=console` põe o link de confirmação no log da API.

## Configuração (`apps/web/.env.local`, não versionado)

| Variável | Para quê |
|---|---|
| `VITE_GOOGLE_WEB_CLIENT_ID` | client ID **Web** do Google; vazio esconde o botão. O mesmo valor vai em `GOOGLE_WEB_CLIENT_ID` no `.env` da raiz (backend) |
| `VOICECOACH_API_PROXY` | para onde o Vite repassa `/v1` (default `http://localhost:8000`) |

## Decisões que valem saber antes de mexer

- **Mesma origem, sempre** (ADR-0077): a sessão é um cookie `HttpOnly`
  restrito a `/v1/auth/web`, e a API não tem CORS. Em dev, o proxy do Vite;
  em produção, um reverse proxy no mesmo domínio.
- **O access token vive só na memória da aba**; recarregar a página o
  recupera pelo cookie. A renovação passa por `navigator.locks` para duas
  abas não se derrubarem (`features/auth/sessaoWeb.ts`, com teste).
- **Visual provisório** (ADR-0078): cor, fonte e espaço só em
  `src/theme/tokens.css`; cada componente com seu `.module.css`. O redesign
  troca esses arquivos, não as telas.
- **Não compartilha UI com `apps/mobile`** (ADR-0002). Textos do produto são
  cópias, com os testes junto.
- Fala com o backend **só** por `@voicecoach/api-client` (ADR-0008).
