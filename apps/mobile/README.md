# apps/mobile — app Expo (React Native)

O carro-chefe do produto (ADR-0001): captura de áudio, playback, navegação e
telas da conversa. Stack decidida no ADR-0002 (Expo + React Native +
TypeScript, áudio via `expo-audio`); as dependências de arranque e o porquê de
cada uma estão no [ADR-0044](../../docs/adr/0044-dependencias-de-arranque-do-app-expo-e-convivencia-com-pnpm.md).

**Estado:** o ciclo completo existe — gravação (CARD-011), upload, consumo do
SSE com recuo para polling e playback encadeado (CARD-012). Desde o CARD-037 o
**iOS físico roda por dev build local**, não por Expo Go (ADR-0054).

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

> Nenhum `.npmrc` é necessário: o Metro resolve os symlinks do pnpm sozinho
> (medido no CARD-011; detalhes e o gatilho para reabrir no ADR-0044 §2).

### No iPhone físico — dev build, **não** Expo Go (ADR-0054)

O Expo Go da App Store está no SDK 54 e o projeto no 57: **um iPhone só instala
pela App Store, e lá não há build mais novo** (ADR-0048). O caminho é compilar o
seu próprio cliente, assinado com Apple ID **gratuito** — custo R$ 0 (ADR-0010).

Com o iPhone ligado por cabo e desbloqueado:

```bash
cd apps/mobile
pnpm run ios:device          # = expo run:ios --device
```

Na **primeira** vez, o build para pedindo assinatura. No Xcode, em
`Signing & Capabilities` do alvo `Voicecoach`: marque *Automatically manage
signing* e escolha o seu Apple ID como *Team* (`Add an Account…` se ele não
estiver lá). Depois, no iPhone: *Ajustes → Geral → VPN e Gerenciamento de
Dispositivo → confiar no certificado*.

O bundle identifier é `com.luanfiszer.voicecoach` (`app.json > ios`). Trocá-lo
faz o iOS tratar o app como **outro** app: instalação nova, e a permissão de
microfone volta ao estado inicial.

### Os 7 dias — o que vai acontecer, e quando

O certificado de conta gratuita **expira em 7 dias**. O sintoma não é uma
mensagem: é o app simplesmente **não abrir**. A cura é repetir
`pnpm run ios:device` com o cabo. Registre a data aqui a cada reinstalação:

| Instalado em | Expira em |
|---|---|
| _(preencher na primeira instalação — CARD-037)_ | _(+7 dias)_ |

### A pasta `ios/` é gerada, não versionada

`expo run:ios` roda `expo prebuild`, que **gera** `ios/` a partir do `app.json`
(Continuous Native Generation). A pasta está no `.gitignore` — e a consequência
que morde é: **editar `Info.plist` ou o projeto do Xcode à mão é trabalho que o
próximo prebuild apaga**. O que precisar entrar no plist entra em
`expo.ios.infoPlist`. Verificado no CARD-037: as três chaves que importam saem
de lá.

```
NSMicrophoneUsageDescription    ← plugin expo-audio
NSLocalNetworkUsageDescription  ← expo.ios.infoPlist
NSAppTransportSecurity: { NSAllowsArbitraryLoads: false,
                          NSAllowsLocalNetworking: true }
```

A última é o que permite HTTP em claro contra o Mac na LAN sem afrouxar o ATS
para a internet inteira.

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
  medicao.tsx           a rota de medição, disparável por deep link (ADR-0047)
src/
  config.ts             app.json > extra + resolução do apiBaseUrl (ADR-0054)
  theme/tokens.ts       paleta, tipografia, alvos — ÚNICA fonte de cor
  api/contrato.ts       aliases dos tipos gerados do OpenAPI
  features/gravacao/    captura: permissão, botão, overlay
  features/turno/       o turn: upload, stream, fila de playback, marcos
ios/                  GERADA por `expo prebuild` — não versionada, não editada
```

## Configuração

`app.json > expo.extra`, lido por `src/config.ts` com validação no import:

| Chave | Hoje | Por quê |
|---|---|---|
| `limiteGravacaoSegundos` | `90` | **Menor que os 120 s** que o backend aceita (`max_turn_audio_duration`). Se o cliente gravar mais que o servidor aceita, o aluno fala, espera o upload e recebe um 413 |
| `sseHabilitado` | `true` | Desligada, exercita o contrato de recuo (`GET /v1/turns/{id}`) do ADR-0026 |
| `apiBaseUrl` | **ausente** | Override explícito. Sem ela, o endereço é **derivado** — ver abaixo |

### O endereço da API não tem default silencioso (ADR-0054 item 6)

`localhost` funcionava no Simulador porque ele compartilha a pilha de rede do
Mac. **Num iPhone, `localhost` é o próprio iPhone** — e a falha resultante não
se lê como configuração errada. A resolução tem três degraus:

1. `extra.apiBaseUrl`, se existir — é o degrau que o **CARD-038** vai usar
   quando o backend sair da LAN e passar a viver atrás de um túnel;
2. o host do bundler (`Constants.expoConfig.hostUri`) com a porta `8000` — no
   aparelho, esse host **já é o IP do Mac**, e ele acompanha sozinho o IP que o
   DHCP trocar: se o Metro alcança o aparelho, o backend também alcança;
3. nada resolveu ⇒ **erro no arranque**, dizendo o que configurar.

O valor efetivo e a origem dele saem no log do Metro:

```
[config] apiBaseUrl=http://192.168.0.12:8000 (origem: bundler)
```

Suba o backend com `--host 0.0.0.0`: em `127.0.0.1` ele só aceita conexão do
próprio Mac, e o iPhone recebe conexão recusada.

### Quando o backend não responde

`packages/api-client` traduz falha de transporte em `ErroDeRede`, que **nomeia o
host tentado** — `não foi possível alcançar http://192.168.0.12:8000 (Network
request failed)`. Sem isso sobra o texto fixo do `fetch` do React Native, que
não diz com quem o app tentou falar. Erro **com** status HTTP é outra coisa
(`ErroDaApi`, Problem Details do ADR-0040): esse é conteúdo para o aluno ler, e
as telas dele são o CARD-027.

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

Três coisas, e isto é regra (ADR-0054 item 3), não recomendação:

- **O microfone.** Ele não existe. Medido em 2026-09-09: quatro gravações do app
  saíram com **pico = 0 e RMS = 0** (silêncio digital), e o `log show` do `tccd`
  e do `SimAudioProcessorService` não registrou evento nenhum — o Simulador não
  chega a abrir o microfone do Mac. O sintoma no produto é o Whisper transcrever
  `'You'`, a alucinação clássica dele diante de silêncio.
- **Qualquer número de latência.** Ele compartilha CPU, rede e disco do Mac
  (ADR-0048).
- **Permissão negada permanentemente.** O estado em que o iOS para de mostrar o
  diálogo não se reproduz lá.

Para os três: `pnpm run ios:device`. Para todo o resto — UI, navegação, estado,
caminho triste — o Simulador continua sendo o ambiente do dia a dia, e é mais
rápido.

## Onde estão as regras

A skill `voicecoach-cliente` (`.claude/skills/`) destila os ADRs em regra
operacional — permissões, áudio, contrato, design, gates. Carregue-a antes de
criar tela, hook ou dependência nova.
