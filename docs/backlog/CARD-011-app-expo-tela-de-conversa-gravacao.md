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
