# ADR-0071 — Login social no cliente: SDK nativo do Google, logo em SVG, Apple ainda desligado

- **Status:** aceito (escrito em 2026-10-01, registrando código escrito pelo desenvolvedor em 2026-09-14 e validado no aparelho físico — ver CARD-060)
- **Data:** 2026-10-01
- **Relacionado:** [ADR-0070](0070-login-social-google-e-apple-juntos-vinculo-por-email.md) (o backend do login social), [ADR-0044](0044-dependencias-de-arranque-do-app-expo-e-convivencia-com-pnpm.md) §4 (config em `app.json > extra`), [ADR-0061](0061-o-primeiro-teste-do-cliente-vitest-sobre-logica-extraida.md) (teste sobre lógica extraída), CARD-060, CARD-053
- **Critérios de obrigatoriedade:** **1 — nova dependência externa** (três pacotes novos em `apps/mobile`: `@react-native-google-signin/google-signin`, `react-native-svg`, `@expo/vector-icons`) e **4 — segurança** (de onde sai o token de identidade que o backend verifica).

## Contexto

O ADR-0070 fechou o backend: `POST /v1/auth/google` recebe um `id_token` e o
verifica contra o JWKS do Google, com `GOOGLE_CLIENT_ID` como audiência. O que
ficou aberto foi **como o app obtém esse `id_token`** — o CARD-060 parou
justamente aí, sem credencial real. Em 2026-09-14 o desenvolvedor criou o
client ID iOS no Google Cloud, escreveu a tela e fez um login real no iPhone
(há uma linha `google` em `social_identities` no banco local dessa data). Este
ADR registra a decisão que esse código tomou, porque ela introduz três
dependências e nenhum ADR a descrevia.

## Decisão

1. **`@react-native-google-signin/google-signin`** obtém o `id_token`, com
   `iosClientId` vindo de `app.json > extra.googleIosClientId` (validado em
   `src/config.ts`, ADR-0044 §4) e o `iosUrlScheme` no config plugin. O
   client ID não é segredo (ADR-0070 §"rota não falha no boot") — o mesmo
   valor é a audiência que o backend confere.
2. **Um único arquivo importa o SDK** (`features/auth/googleSignIn.ts`),
   devolvendo só a string do token. O núcleo testável
   (`sessaoAutenticada.loginGoogle`) recebe o token pronto — é a fronteira
   nativa que o ADR-0061 manda não mockar. Cancelamento do aluno é uma
   exceção própria (`LoginGoogleCancelado`) e **não** vira mensagem de erro.
3. **`react-native-svg`** desenha o "G" oficial em quatro cores
   (`LogoGoogle.tsx`); **`@expo/vector-icons`** fornece o glifo monocromático
   da Apple. Fonte de ícone pinta o glifo inteiro de uma cor só — por isso o
   logo do Google não podia vir dela.
4. **Botão "Continuar com a Apple (em breve)" aparece desabilitado.** Falta o
   `APPLE_CLIENT_ID`, que depende do Apple Developer Program (CARD-053).

## Alternativas consideradas

### A — `expo-auth-session` (OAuth pelo navegador)
- **Prós:** sem módulo nativo novo; um fluxo genérico serviria aos dois
  provedores.
- **Por que foi rejeitada:** o próprio Expo deixou de recomendar o provedor
  Google do `expo-auth-session` em favor do SDK nativo; o fluxo pelo navegador
  troca a folha nativa de contas do sistema por um redirect com mais
  configuração (esquema de URL, client "web") e mais atrito para o aluno. O
  app já roda em development build (CARD-037), então módulo nativo não custa
  nada a mais.

### B — Logo do Google como PNG (`Image`), sem `react-native-svg`
- **Prós:** zero dependência nova.
- **Por que foi rejeitada:** precisaria de três resoluções (`@1x/@2x/@3x`) e
  ainda serrilharia em tamanhos fora delas; `react-native-svg` é módulo
  mantido pelo próprio ecossistema Expo e servirá a qualquer ícone vetorial
  futuro. Custo aceito: um módulo nativo a mais no build.

### C — Esconder o botão da Apple até existir credencial
- **Prós:** nenhuma promessa visível que o app ainda não cumpre.
- **Por que foi rejeitada (por ora):** deixar o botão "em breve" mantém o
  layout final da tela estável para o teste de uso. **Decisão autônoma,
  pendente de revisão humana** — ver Consequências.

## Consequências

- **Bloqueante de publicação, não de desenvolvimento:** a Guideline 4.8 da
  Apple exige Sign in with Apple **funcional** quando há login de terceiro. O
  app não vai à loja com o botão desabilitado — o CARD-053 (conta Apple) é
  pré-requisito do fechamento do CARD-060.
- **Android não está configurado:** no Android, o SDK só devolve `idToken`
  com `webClientId` configurado, e o backend teria de aceitar mais de uma
  audiência. Nenhum dos dois existe hoje; vale quando o Android entrar no
  escopo de teste.
- Três módulos nativos a mais exigem rebuild do development build (`pnpm run
  ios:device`), não só reload do Metro.
