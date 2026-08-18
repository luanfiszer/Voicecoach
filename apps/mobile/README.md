# apps/mobile — app Expo (React Native)

**Ainda vazio.** O bootstrap do Expo entra no card da Fase 1; o CARD-001 só
reserva o lugar e declara a fronteira.

## O que mora aqui

O carro-chefe do produto (ADR-0001): captura de áudio, playback, navegação e
telas da conversa. Stack decidida no ADR-0002: Expo + React Native +
TypeScript, áudio via `expo-audio`.

## Regra de fronteira

> **App é bootstrap e UI de plataforma — não é onde regra de negócio mora.**

- Fala com o backend **apenas** através de `packages/api-client` (tipos gerados
  do OpenAPI — ADR-0008). Nunca monta URL nem tipo de request na mão: contrato
  duplicado é drift garantido.
- Nada em `apps/*` é importado por `packages/*`. A seta aponta sempre de app
  para pacote, nunca ao contrário.
- Token de sessão em `expo-secure-store` (Keychain/Keystore), nunca em
  `AsyncStorage` — ADR-0007.
