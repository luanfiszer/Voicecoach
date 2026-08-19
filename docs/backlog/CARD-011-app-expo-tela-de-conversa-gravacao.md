# CARD-011 — App Expo: esqueleto, tela de conversa e gravação de áudio

- **ID:** CARD-011 · **Épico:** Fase 1 — Fatia vertical
- **Plataforma:** mobile · **Esforço:** M · **Status:** backlog
- **Dependências:** CARD-001 (workspace); contrato pode ser mockado até CARD-010

## Contexto

ADR-0002 (Expo + TS no monorepo). Primeira sessão de React Native do
desenvolvedor — o card é deliberadamente contido: uma tela, um fluxo.

## Problema

Não existe app. O maior desconhecido do projeto (captura de áudio em RN +
permissões) precisa ser atacado agora, como decidido no roadmap.

## Proposta técnica

- `apps/mobile` com `create-expo-app` (TS), estrutura mínima de navegação
  (expo-router) com uma tela de conversa.
- Gravação com `expo-audio`: pedir permissão de microfone (fluxo de negado
  incluído), gravar com **limite de duração** (config — lição §7.4),
  visualizar estado (idle/gravando/pronto), regravar/descartar.
- Reprodução local do que foi gravado (validação antes de existir backend na
  jornada).
- Rodar no aparelho físico via Expo Go.

## Escopo

- **In:** o acima. **Out:** upload/polling/playback da resposta (CARD-012);
  qualquer estilização além do funcional.
- **Herdado do CARD-004:** este é o card em que nasce a skill
  `voicecoach-cliente` (`.claude/skills/`), irmã da `voicecoach-arquitetura`.
  Ela foi adiada de propósito — regra escrita antes de existir tela é letra
  morta. Fontes a destilar: ADR-0002 (Expo + web separada), ADR-0007 (token em
  `expo-secure-store`, nunca AsyncStorage), ADR-0008 (tipos gerados do OpenAPI,
  `min_supported_app_version`), ADR-0003 (upload + polling com backoff).

## Critérios de aceite

- **Dado** primeira abertura, **quando** toco em gravar, **então** o app pede
  permissão; negada ⇒ mensagem com caminho para configurações.
- **Dado** gravação ativa, **quando** atinge o limite de duração, **então**
  para sozinha e informa.
- **Dado** um áudio gravado, **então** consigo ouvi-lo e regravar.
- Funciona no aparelho físico (iOS ou Android — o que estiver à mão).

## Riscos

Primeiro contato com RN: estimativa pode estourar — se estourar, o corte é
na UX (estados mínimos), nunca no fluxo de permissão.

## Objetivo de aprendizado

O modelo mental do RN vs React web: componentes nativos (View/Text/Pressable
vs div/button), o ciclo de permissões de plataforma, e hooks sobre recursos
nativos (expo-audio) — onde o "é só React" termina.

## Ajuste da reconstrução (2026-08-19)

**O card sobrevive praticamente intacto** — gravação, permissões e limite de
duração não mudam com a cascata. Dois acréscimos:

- **Por que agora:** é o único card do caminho crítico que não depende de nada
  do backend e pode correr em paralelo com 006–010. Deixá-lo para o fim
  atrasaria a medição ponta a ponta, que é o que valida o alvo de 1,8 s.
- **Um requisito novo, vindo do [ADR-0026](../adr/0026-entrega-progressiva-por-sse-com-polling-como-contrato-de-recuo.md):**
  ao montar o app, verificar **dentro do Expo Go** se o consumo de SSE é viável
  (`react-native-sse` ou `fetch` com streaming). Descobrir isso no CARD-012, com
  a fatia inteira pronta, é caro; aqui custa meia hora. Se exigir dev build, o
  CARD-012 já entra sabendo qual recuo vai usar.
- A skill `voicecoach-cliente` continua nascendo aqui, e agora destila também o
  ADR-0026 (transporte) e o ADR-0024 (URL de trecho expirada).
