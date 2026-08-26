---
name: voicecoach-cliente
description: Regras do CLIENTE do Voicecoach (app Expo/React Native em apps/mobile e a web Vite em apps/web) destiladas dos ADRs. Use ao criar tela, componente ou hook no app, decidir se uma dependência de cliente pode entrar, consumir a API, lidar com permissão de plataforma, áudio, token de sessão ou tokens de design. Não cobre o backend Python (ver voicecoach-arquitetura).
---

# Cliente — Voicecoach

Regras **destiladas dos ADRs** (`docs/adr/`) e do design (`docs/design/`).
**Nenhuma regra aqui sem fonte.** O *porquê* de cada uma, com o gatilho para
reavaliá-la, está em [REFERENCE.md](REFERENCE.md).

> **Cobertura desta skill:** ADRs 0001, 0002, 0003, 0007, 0008, 0010, 0023,
> 0024, 0026, 0043, 0044, 0045, 0046, 0047, e o style guide de
> `docs/design/README.md`. Se a skill
> contradisser um ADR, **o ADR ganha**.
>
> O produto deste projeto é o conhecimento do desenvolvedor; o código é
> subproduto (CLAUDE.md). Ao aplicar uma regra, saiba citar o ADR que a
> originou — regra sem lastro é opinião do agente disfarçada de convenção.

## Quem manda quando as fontes divergirem

| Fonte | O que é | Quando ganha |
|---|---|---|
| `biome.json`, `apps/mobile/tsconfig.json`, `package.json` | **lei executável** — lint, formatação, `strict`, scripts | sempre. Se a skill disser outra coisa, a skill está errada |
| `packages/api-client/src/schema.d.ts` | o contrato, **gerado** do OpenAPI | é a verdade sobre a API. Nunca se edita à mão |
| `docs/adr/` | a decisão, com alternativas e trade-offs | é a origem de toda regra abaixo |
| `docs/design/README.md` + `artboards/` | direção visual e microcopy | manda na aparência; **não** manda na sequência de estados (ver §Design) |
| **esta skill** | digest operacional: "onde ponho X" | orienta; nunca contradiz as quatro acima |

## Escopo

Só o **cliente**: `apps/mobile` (Expo/RN), `apps/web` (Vite, ainda vazio) e o
consumo de `packages/api-client`. O backend Python tem skill própria
(`voicecoach-arquitetura`).

## O que o produto é (a régua contra overengineering)

Tutor de inglês **por conversa de áudio**. O mobile é o carro-chefe (ADR-0001);
a web é companion (progresso, histórico, conta) e **não compartilha UI com o
mobile** — `react-native-web` foi rejeitado explicitamente (ADR-0002).
Antes de propor peça nova (state manager, biblioteca de UI, animação,
navegação exótica), cheque a **Parte F da visão** e o §"O que NÃO entrou" do
ADR-0044: o corte já foi decidido, com gatilho objetivo escrito.

## Mapa: onde mora o quê

```
apps/mobile/
  app/                  ← ROTAS. expo-router: o arquivo É a rota (ADR-0044)
    _layout.tsx           layout raiz (SafeAreaProvider, Stack)
    index.tsx             "/" — monta a tela, não implementa a tela
  src/
    config.ts           ← app.json > extra, validado no import (ADR-0044 §4)
    theme/tokens.ts     ← paleta, tipografia, alvos. ÚNICA fonte de cor
    api/contrato.ts     ← aliases dos tipos gerados (ADR-0008)
    features/<nome>/    ← a feature inteira: hook de estado + componentes
```

```
packages/api-client/src/
  schema.d.ts         ← GERADO do OpenAPI. Nunca editado à mão (ADR-0008)
  cliente.ts          ← criarCliente({baseUrl, fetch?, token?}) (ADR-0046)
  eventos.ts          ← leitura do text/event-stream (ADR-0044, ADR-0046)
  index.ts            ← a porta de entrada do pacote
```

| Preciso de… | Vai em | Fonte |
|---|---|---|
| uma tela nova | `app/<rota>.tsx`, montando um componente de `src/features/` | ADR-0044 §3 |
| estado de uma feature | um hook em `src/features/<nome>/use<Nome>.ts` | — |
| cor, tamanho de fonte, alvo de toque | `src/theme/tokens.ts` — **nunca** hex no componente | design §17 |
| um valor configurável (limite, URL) | `app.json > extra` + validação em `src/config.ts` | ADR-0044 §4 |
| um tipo da API | `src/api/contrato.ts`, alias do gerado | ADR-0008 |
| chamar a API | `criarCliente()` de `packages/api-client` — **nunca** montar URL à mão | ADR-0008, ADR-0046 |
| dedup, recuo, reconexão, `AppState` | a máquina de estados **no app** — o client não faz nada disso | ADR-0046 §3 |
| subir um arquivo do aparelho | converta para `Blob` primeiro (`arquivoLocal.ts`) | ADR-0046 §4 |
| guardar token de sessão | `expo-secure-store` (Keychain/Keystore) | ADR-0007 |

## O que NÃO fazer

- ❌ **Escrever tipo da API à mão.** Se o backend mudou, **regenere**. Tipo
  duplicado é drift garantido, e o ganho do monorepo é a quebra em *build*
  (ADR-0008). Editar `schema.d.ts` é bug esperando acontecer.
- ❌ **Montar URL do backend em componente.** A fronteira é
  `packages/api-client` (`apps/mobile/README.md`, ADR-0008).
- ❌ **Importar de `apps/*` dentro de `packages/*`.** A seta aponta de app para
  pacote, nunca ao contrário.
- ❌ **Compartilhar componente de UI entre `apps/mobile` e `apps/web`.** Decisão,
  não esquecimento (ADR-0002, Alternativa A).
- ❌ **Guardar token em `AsyncStorage`.** É `expo-secure-store`, sempre
  (ADR-0007).
- ❌ **Hex, tamanho de fonte ou `48`/`84` solto em `StyleSheet`.** Vai em
  `theme/tokens.ts`.
- ❌ **Usar `expo-av`.** Descontinuado; é `expo-audio` (ADR-0002, ADR-0044). A
  API é **diferente**, não é renomeação — e o erro se disfarça de problema de
  permissão.
- ❌ **Tratar permissão como estado do app.** Ela é da **plataforma**: consulte,
  não guarde (§Permissões).
- ❌ **`setTimeout` para limitar duração de gravação.** Mede o tempo do
  JavaScript, não o do microfone. Reaja a `durationMillis` (ADR-0044 §4).
- ❌ **Sair para dev build porque algo não funcionou no Expo Go.** Isso é
  **achado**, e vira ADR ou dívida no card (ADR-0002, ADR-0010).
- ❌ **`any`, `!` (non-null assertion) e dependência de hook omitida.** São erro
  no Biome, não aviso (ADR-0043).
- ❌ **`formData.append('audio', { uri, name, type })`.** É o idioma que todo
  tutorial de RN ensina e **ele não funciona** no Expo Go SDK 57: `Unsupported
  FormDataPart implementation`. Medido — só `Blob` passa (ADR-0046 §4).
- ❌ **Reescrever o host de uma URL assinada.** O `Host` entra na assinatura
  SigV4 (`X-Amz-SignedHeaders=host`): trocar depois dá 403 `SignatureDoesNotMatch`,
  e **não há conserto no cliente**. Quem assina com o host certo é o servidor,
  por `S3_PUBLIC_ENDPOINT_URL` (ADR-0045).
- ❌ **Medir com um relógio mais grosso que o critério.** O
  `playbackStatusUpdate` do `expo-audio` tem `updateInterval` default de
  **500 ms**; medir um gap de 150 ms com ele produz o número do relógio
  (ADR-0047 §6).

## Permissões: são três estados, não dois

`concedida` · `indefinida` (pode perguntar) · **`negada-permanentemente`**.

O terceiro existe porque no iOS, **depois da primeira negação**,
`requestRecordingPermissionsAsync()` volta negado **na hora, sem diálogo**. O
único caminho de volta é `Linking.openSettings()`. Traduza sempre o
`PermissionResponse` (`granted` + `canAskAgain`) para os três, e trate o
terceiro com o **artboard 13** (microcopy pronta: "Precisamos do microfone" →
*Abrir Ajustes* / *Agora não*).

> **O Simulador não prova permissão.** O microfone é o do Mac e o estado
> "negada permanentemente" não se reproduz. Esse fluxo se aceita **em aparelho
> físico**, ou você testou outra coisa.
>
> **E o aparelho físico não é alcançável por Expo Go** (ADR-0048): a App Store
> está no SDK 54 e o projeto no 57. O caminho é `npx expo run:ios --device`
> (dev build local, custo zero). Não invente que o Simulador basta — a dívida
> está declarada no CARD-012, e ela é do canal, não do trabalho.

## Áudio (ADR-0002, ADR-0044)

- Gravação e playback por **`expo-audio`** — `useAudioRecorder` +
  `useAudioRecorderState` (que faz polling do lado nativo) e `useAudioPlayer` +
  `useAudioPlayerStatus`.
- **Limite de duração é regra de produto**, vem de configuração e é **menor**
  que `max_turn_audio_duration` do backend (hoje 120 s). Ao atingir: para
  sozinha **e informa**.
- No iOS, `setAudioModeAsync({ allowsRecording: true })` joga o playback para o
  alto-falante do ouvido. **Desligue `allowsRecording` ao terminar de gravar**,
  ou "ouvir o que gravei" sai baixinho.
- **Nada de V2 aqui** (ADR-0003): sem módulo nativo, sem barge-in, sem áudio
  contínuo.

## Falar com o backend (ADR-0008, ADR-0026, ADR-0024)

- Tipos **gerados**; regeneração e o job de CI estão em
  `packages/api-client/README.md`.
- Evolução é **aditiva**: campo novo pode aparecer, e o cliente tolera o
  desconhecido. Nunca assuma que um campo opcional existe.
- **Transporte da entrega progressiva: `fetch` lendo `response.body` como
  stream** — medido no Expo Go, sem polyfill e sem dev build (ADR-0044).
  Cuidado: o separador de eventos é **`\r\n\r\n`**; procurar `\n\n` faz o
  stream chegar e nenhum evento ser reconhecido, **sem erro**.
- **Os cinco payloads do SSE são tipos GERADOS** desde o ADR-0046. Se um evento
  novo aparecer sem tipo, o furo é no `responses` da rota do stream — não se
  escreve o tipo à mão para contornar.
- **A `Idempotency-Key` é parâmetro do `enviarTurn`**, gerada **uma vez** ao
  concluir a gravação. Gerá-la por tentativa duplica turn (ADR-0042/0046 §2).
- **Dedup por `id` de evento é do cliente também**: histórico e canal ao vivo
  podem entregar o mesmo evento, e o sintoma é o professor repetindo frases
  (ADR-0041 item 3). `feedback` **não** volta na retomada — nada pode esperá-lo
  para sair do carregamento.
- **O polling (`GET /v1/turns/{id}`) é o contrato de recuo e precisa continuar
  funcionando** (ADR-0026 item 4). Dois caminhos, ambos exercitados, ou o recuo
  apodrece.
- **URL de trecho é assinada e expira** (ADR-0024). Trecho expirado com `full`
  presente ⇒ toque o inteiro; ambos expirados ⇒ áudio indisponível, texto e
  correções preservados. **Nunca** tratar como erro fatal.

## Design (`docs/design/`)

- **Siga:** paleta, tipografia, tom, microcopy, anatomia do card de correção,
  alvo mínimo 48 px, botão de gravar 84 px (**pulso = gravando, quadrado =
  parar**).
- **Reconcilie:** a **sequência de estados** do design é de 2026-08-17, anterior
  à cascata. **Hoje o áudio vem primeiro**, em 3–6 trechos, e o texto do
  feedback fecha depois (ADR-0022/0023). Telas montadas na ordem desenhada
  nascem erradas.
- **Não implemente:** `reiniciar demo` / `a. idle` do artboard 01 — andaime de
  apresentação (premissa **não confirmada** em
  `docs/reconciliacao-telas-dominio.md`).
- **Não existe artboard do estado "gravando".** Derive do style guide; não
  invente tela nova.

## Quality gates (ADR-0043)

| Anel | O que roda |
|---|---|
| 1 — agente | `biome check --write <arquivo>` + `pnpm -r run typecheck` a cada edição de `.ts`/`.tsx` |
| 2 — pre-commit | `biome check --write` em `^(apps\|packages)/` + `tsc` sobre o projeto inteiro |
| 3 — CI | job `mobile`: `pnpm install --frozen-lockfile`, `pnpm run lint`, `pnpm run typecheck` |

Da raiz: `pnpm run gates`. **Não há gate de teste no cliente** — adiado com
gatilho escrito (ADR-0043 item 6); não invente um sem ADR.

## Antes de fechar (checklist de PR)

- [ ] `pnpm run gates` verde (Biome + `tsc --strict`)
- [ ] Nenhum tipo de API escrito à mão; `schema.d.ts` regenerado se o backend
      mudou (ADR-0008)
- [ ] Nenhum hex/tamanho/alvo fora de `theme/tokens.ts`
- [ ] Permissão tratada nos **três** estados, com caminho para os Ajustes
- [ ] Dependência nova tem ADR **com a alternativa descartada** e checou a
      Parte F da visão (critério 1 de `docs/adr/README.md`)
- [ ] O que só o **aparelho físico** prova foi verificado lá, não no Simulador —
      e, se não foi, a dívida está **escrita** com o motivo (ADR-0048)
- [ ] Card em `docs/backlog/` atualizado; **regra do explicador** cumprida
- [ ] Regra desta skill que não bateu com o código virou ADR ou correção —
      **nunca afrouxada em silêncio**
