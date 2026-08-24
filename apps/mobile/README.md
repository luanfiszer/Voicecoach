# apps/mobile — app Expo (React Native)

O carro-chefe do produto (ADR-0001): captura de áudio, playback, navegação e
telas da conversa. Stack decidida no ADR-0002 (Expo + React Native +
TypeScript, áudio via `expo-audio`); as dependências de arranque e o porquê de
cada uma estão no [ADR-0044](../../docs/adr/0044-dependencias-de-arranque-do-app-expo-e-convivencia-com-pnpm.md).

**Estado:** a tela de conversa existe com o ciclo de gravação completo
(CARD-011). Não há upload, nem consumo de SSE na tela, nem playback da resposta
do professor — isso é o CARD-012.

## Como rodar

Da raiz do repositório, uma vez:

```bash
pnpm install
```

Depois, com o Simulador iOS aberto:

```bash
cd apps/mobile
pnpm expo start --ios
```

No aparelho físico: `pnpm expo start` e leia o QR code com o Expo Go.
**O aparelho físico não é opcional** para permissão de microfone — ver abaixo.

> Nenhum `.npmrc` é necessário: o Metro resolve os symlinks do pnpm sozinho
> (medido no CARD-011; detalhes e o gatilho para reabrir no ADR-0044 §2).

## Quality gates (ADR-0043)

Da raiz:

```bash
pnpm run gates        # biome check + tsc --noEmit (strict) em todo o workspace
pnpm run lint:fix     # aplica formatação e correções seguras
```

Rodam também no `pre-commit` e no CI (job `mobile`). **Não há gate de teste
automatizado** — adiado com gatilho escrito no ADR-0043 item 6.

## Estrutura

```
app/                  ROTAS (expo-router: o arquivo É a rota)
  _layout.tsx           layout raiz
  index.tsx             "/" — monta a tela de conversa
  spike-sse.tsx         SPIKE do ADR-0026, descartável — sai no CARD-012
src/
  config.ts             app.json > extra, validado no import
  theme/tokens.ts       paleta, tipografia, alvos — ÚNICA fonte de cor
  api/contrato.ts       aliases dos tipos gerados do OpenAPI
  features/gravacao/    a feature: hook de estado + componentes
```

## Configuração

`app.json > expo.extra`, lido por `src/config.ts` com validação no import:

| Chave | Hoje | Por quê |
|---|---|---|
| `limiteGravacaoSegundos` | `90` | **Menor que os 120 s** que o backend aceita (`max_turn_audio_duration`). Se o cliente gravar mais que o servidor aceita, o aluno fala, espera o upload e recebe um 413 |
| `apiBaseUrl` | `http://localhost:8000` | Funciona no Simulador. **Em aparelho físico, troque pelo IP da máquina** na rede local |

## Regra de fronteira

> **App é bootstrap e UI de plataforma — não é onde regra de negócio mora.**

- Fala com o backend **apenas** através de `packages/api-client` (tipos gerados
  do OpenAPI — ADR-0008). Nunca monta URL nem tipo de request na mão: contrato
  duplicado é drift garantido.
- Nada em `apps/*` é importado por `packages/*`. A seta aponta sempre de app
  para pacote, nunca ao contrário.
- Token de sessão em `expo-secure-store` (Keychain/Keystore), nunca em
  `AsyncStorage` — ADR-0007. *(Ainda não há auth; a regra está escrita para não
  nascer errada.)*

> Estas três fronteiras **não têm gate automático** (o backend tem
> `import-linter`; aqui não há equivalente). Dívida declarada na skill
> `voicecoach-cliente`.

## O que o Simulador NÃO prova

- **Permissão negada permanentemente.** O Simulador não reproduz o estado em
  que o iOS para de mostrar o diálogo. Esse fluxo se aceita **em aparelho
  físico**, ou você testou outra coisa.
- **O microfone real** (no Simulador é o do Mac) e a latência de captura.

## Onde estão as regras

A skill `voicecoach-cliente` (`.claude/skills/`) destila os ADRs em regra
operacional — permissões, áudio, contrato, design, gates. Carregue-a antes de
criar tela, hook ou dependência nova.
