# apps/web — app web companion (Vite + React)

**Ainda vazio.** O bootstrap do Vite entra no card da Fase 1; o CARD-001 só
reserva o lugar e declara a fronteira.

## O que mora aqui

O companion (ADR-0001): progresso, histórico de sessões, correções acumuladas,
erros recorrentes, gestão de conta. Stack decidida no ADR-0002: Vite + React +
TypeScript — React web "de verdade", com DOM/CSS e o ecossistema de gráficos e
tabelas disponível.

## Regra de fronteira

> **App é bootstrap e UI de plataforma — não é onde regra de negócio mora.**

- Fala com o backend **apenas** através de `packages/api-client` (ADR-0008).
- Nada em `apps/*` é importado por `packages/*`.
- **Não compartilha componentes de UI com `apps/mobile`.** Isso é decisão, não
  esquecimento: o ADR-0002 rejeitou explicitamente unificar a UI via
  `react-native-web`. A sobreposição real de telas entre dashboard e app de
  conversa é pequena, e o custo de conciliar os dois mundos é alto.
