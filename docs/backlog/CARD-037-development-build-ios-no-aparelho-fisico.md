# CARD-037 — Development build iOS no aparelho físico: paga a dívida do ADR-0048

- **ID:** CARD-037
- **Épico:** Fase 1 — fechamento honesto (o número que faltou)
- **Plataforma:** mobile/infra · **Esforço:** M · **Status:** **preparação concluída — aguardando o aparelho** (sessão de 2026-09-09)
- **Dependências:** CARD-011, CARD-012, [ADR-0048](../adr/0048-o-expo-go-da-loja-ficou-para-tras-e-o-aparelho-fisico-vira-divida.md),
  [ADR-0002](../adr/0002-stack-de-cliente-expo-mais-web-separada.md),
  [ADR-0010](../adr/0010-politica-de-custo-projeto-pessoal.md)

## Contexto

O ADR-0048 fechou a Fase 1 com uma dívida **declarada por escrito**: a
verificação em aparelho físico deixaria de ser feita por Expo Go e viraria
"card próprio". **Este é o card que o ADR prometeu e que nunca foi criado** —
a ausência dele foi encontrada em 2026-09-09, ao varrer o backlog atrás de
pendências.

Classificação do débito (template): **débito de negócio, não técnico.** O código
do CARD-011 e do CARD-012 está correto — e a sessão de 2026-09-09 provou isso
medindo. O que faltou nunca foi implementação: foi um **ambiente de execução**
capaz de entregar microfone de verdade. Não há nada a refatorar aqui; há um
canal a trocar.

### O que a sessão de 2026-09-09 mediu

O desenvolvedor relatou que o app "não ouve o microfone". A investigação
produziu evidência, não suposição:

| Evidência | Resultado |
|---|---|
| Últimas 4 gravações do app no Simulador (`.m4a` do cache do Expo Go) | duração e formato **corretos**; **pico = 0, RMS = 0** |
| Áudio gerado no host com `say` e enviado ao mesmo pipeline | **pico = 25480, RMS = 5263** — turn `completed` em 4,93 s, transcrição exata, 2 correções de gramática detectadas |
| Transcrição das gravações do Simulador que chegaram ao backend | `'You'` — alucinação clássica do Whisper diante de silêncio digital |
| `log show` de `tccd` e `SimAudioProcessorService` durante a gravação | **nenhum evento** — o Simulador não chega a abrir o microfone do host |
| `Info.plist` de `Simulator.app` e de `SimAudioProcessorService.xpc` | **nenhum** declara `NSMicrophoneUsageDescription` — por isso o alerta do macOS nunca aparece |
| `defaults read com.apple.iphonesimulator` | sem chave de áudio: `I/O → Audio Input` está no **default do sistema**, e não é a causa |

Conclusão: **o pipeline inteiro funciona; o microfone do Simulador é que não
existe.** É limitação conhecida do Simulador, agravada no Xcode 26 / iOS 26.x
(relatos de `prepareToRecord()` devolvendo `false` e de `getUserMedia` falhando
com *"No AVAudioSessionCaptureDevice device"*).

## Problema

Três consequências que só o aparelho físico resolve, e que hoje estão paradas:

1. **CARD-011 tem pendência aberta:** o estado `negada-permanentemente`
   (`useGravacao.ts`) e o `OverlayPermissao` nunca foram exercitados contra o
   ciclo real de permissão do iOS — `Linking.openSettings()` incluído.
2. **CARD-012 fechou com dívida declarada:** p50 de **2,47 s** contra alvo de
   2,4 s, medido no Simulador, que *"compartilha CPU, rede e disco do Mac"*
   (ADR-0048). O critério de saída da fase pede o número **em aparelho físico**,
   e esse número não existe.
3. **Nenhuma fala real jamais atravessou o produto.** Todo teste ponta a ponta
   até hoje usou áudio sintético ou silêncio. STT contra voz humana com ruído
   ambiente é um comportamento não observado.

## Proposta técnica

**Development build local, assinado com conta Apple gratuita.** Decidido pelo
desenvolvedor em 2026-09-09, com as alternativas na mesa:

| Rota | Custo | Instalação | Validade |
|---|---|---|---|
| **Conta gratuita (escolhida)** | **R$ 0** | Mac + cabo | **7 dias** |
| Apple Developer | US$ 99/ano | TestFlight, pelo ar | 90 dias |

A conta gratuita **preserva o ADR-0010** (*"infra jamais custa dinheiro sem ADR
novo"*); a paga exigiria ADR. O preço aceito é a reinstalação semanal por cabo —
registrada aqui para não virar surpresa na sessão seguinte.

O `apiBaseUrl` passa de `localhost` para o IP do Mac na LAN. Ele já é
**configurável** (`app.json > expo.extra`, lido e validado em `src/config.ts`),
então a mudança é de valor, não de arquitetura — mas `localhost` não pode
continuar como default silencioso: num aparelho físico ele aponta para o próprio
iPhone e falha de um jeito que não se lê como configuração errada.

> ### Decisão arquitetural embutida — **ADR obrigatório antes da implementação**
>
> Critério **6 de `docs/adr/README.md` — contraria uma convenção estabelecida.**
> O ADR-0002 elegeu o Expo Go como estratégia de execução do cliente. Este card
> o abandona em iOS. O ADR-0048 **declarou a dívida** mas não decidiu o
> substituto: ele explicitamente deixou a escolha para o card. Também toca o
> critério **5 (difícil de reverter)** — dev build muda o fluxo de execução de
> toda sessão de mobile daqui para frente.
>
> O ADR deve registrar: dev build local vs. EAS Build na nuvem; conta gratuita
> vs. paga com os números acima; e o que acontece com o Simulador (continua
> sendo o ambiente do dia a dia para UI, deixa de valer para áudio e latência).

A medição **não precisa de código novo**: `src/features/turno/marcos.ts` já
define os quatro marcos com o método escrito (`parouDeFalar`, `uploadCompleto`,
`primeiroChunk`, `primeiroAudivel`), já calcula `p50`, e a tela `app/medicao.tsx`
já existe. Este card **usa** essa instrumentação num aparelho — não a reescreve.

## Refinamento obrigatório — cache e limites

1. **TTL:** não se aplica — o card não introduz cache.
2. **Gatilho de invalidação:** não se aplica.
3. **Política de limite:** não se aplica — nenhum endpoint é criado ou alterado.
   O backend segue acessível **apenas na LAN**; a exposição à internet e o
   porteiro (`INVITE_CODE`, ADR-0010 item 5) são o **CARD-038**.
4. **Timeout, retry e desfecho:** o app já fala com uma dependência externa (a
   API), com política estabelecida nos CARD-012 e CARD-026 — este card **não a
   altera**. O que ele acrescenta é um **modo de falha novo**: o IP do Mac na
   LAN muda por DHCP, ou o Mac dorme, e o app passa a apontar para lugar nenhum.
   Isso não é timeout de dependência, é configuração obsoleta — e o desfecho
   esperado é a mensagem de erro dizer **qual host** falhou, não um "algo deu
   errado" genérico.

## Escopo

- **In:** dev build iOS assinado com conta gratuita; instalação no iPhone do
  desenvolvedor; `apiBaseUrl` apontando para o IP do Mac na LAN, com o default
  `localhost` deixando de ser silencioso; ADR da troca de ambiente de execução;
  reexecução da medição do CARD-012 em aparelho real; fechamento das pendências
  de permissão do CARD-011; registro do procedimento de reinstalação (7 dias) no
  `README` do app.
- **Out:** túnel/exposição do backend na internet e `INVITE_CODE` (**CARD-038**);
  TestFlight e conta paga (exigiriam ADR de custo); build Android; publicação em
  loja; qualquer mudança no backend.

## Divisão do trabalho — agente e desenvolvedor

Este card **não é executável de ponta a ponta por um agente**, e isso é
característica dele, não defeito: assinar binário, plugar cabo e falar num
microfone são atos físicos. Declarado aqui para que a sessão não descubra isso
no meio.

| Etapa | Quem |
|---|---|
| ADR da troca de ambiente de execução | agente (com a decisão já tomada) |
| `apiBaseUrl` deixar de cair em `localhost` em silêncio | agente |
| Erro de rede nomear o host inalcançável | agente |
| Procedimento de reinstalação dos 7 dias no `README` | agente |
| Gerar o dev build e **assinar** com o Apple ID | **desenvolvedor** |
| Instalar no iPhone e confiar no certificado | **desenvolvedor** |
| Gravar 5 falas reais e colher o `p50` | **desenvolvedor** |
| Exercitar a negação de permissão até `negada-permanentemente` | **desenvolvedor** |
| Registrar os números medidos no card | agente, com os dados do desenvolvedor |

A sessão do agente vai até a preparação estar completa, **para**, e entrega ao
desenvolvedor um roteiro do que fazer com o aparelho na mão.

## Critérios de aceite

- **Dado** o iPhone do desenvolvedor com o dev build instalado, **quando** ele
  abre o app, **então** a tela de conversa carrega e o `apiBaseUrl` efetivo
  aparece no log de arranque — não `localhost`.
- **Dado** uma fala real gravada **no aparelho**, **quando** o turn completa,
  **então** o `.m4a` enviado tem **pico > 0** e a transcrição corresponde ao que
  foi dito — o oposto exato do `'You'` que o Simulador produziu.
- **Dado** 5 turns consecutivos no aparelho, **então** o `p50` de
  `parouDeFalar → primeiroAudivel` é registrado no card, **com o número escrito
  mesmo se estourar 2,4 s** — o critério é *medir e registrar*, não *bater a
  meta* (o ADR-0048 já estabeleceu que número honesto vale mais que número bom).
- **Dado** o gap entre trechos medido no aparelho, **então** o resultado é
  comparado ao do Simulador (< 150 ms) e a diferença é registrada.
- **Dado** que o aluno nega a permissão de microfone e depois nega de novo,
  **então** o app entra em `negada-permanentemente`, o `OverlayPermissao`
  aparece, e `Linking.openSettings()` abre os Ajustes do iOS no app correto —
  **o caminho que nunca foi exercitado**.
- **Dado** o Mac desligado ou fora da rede, **quando** o app tenta enviar,
  **então** o erro exibido nomeia o host inalcançável.
- **Dado** `uv run pytest --cov --cov-fail-under=80` e os gates do cliente,
  **então** seguem verdes — este card não deve alterar o backend.

## Riscos

- **A assinatura gratuita é o ponto mais provável de atrito.** Apple ID sem
  conta de desenvolvedor, `Signing & Capabilities` no Xcode, e o iPhone pedindo
  para confiar no certificado em *Ajustes → Geral → VPN e Gerenciamento de
  Dispositivo*. **Plano B:** se o build local travar, `eas build --local` ou
  build pela nuvem — sem sair da conta gratuita, para não contrariar o ADR-0010.
- **Os 7 dias vão expirar no meio de um card futuro**, e o sintoma é o app
  simplesmente não abrir. Mitigação: registrar o procedimento no `README` do app
  e a data de validade na execução deste card.
- **O número do aparelho pode ser pior que o do Simulador** (rede Wi-Fi real,
  CPU do iPhone decodificando AAC). É resultado, não fracasso — o card manda
  registrar o que der.
- **DHCP muda o IP do Mac** e o app para de funcionar sem motivo aparente.
  Mitigação: IP reservado no roteador, ou aceitar e documentar.

## Objetivo de aprendizado

> Obrigatório e específico.

**Entender o que um "dev build" do Expo realmente é, e por que ele não tem
paralelo no mundo .NET.** Especificamente: que o Expo Go é um *app hospedeiro*
que carrega o seu JavaScript por rede — mais próximo de um runtime plugável que
de um executável seu —, e que o dev build é o oposto: um binário nativo que
**você** assina, contendo os módulos nativos que o seu `package.json` pede.
Daí a incompatibilidade de SDK do ADR-0048 fazer sentido: o Expo Go não pode
carregar código que exige módulo nativo que ele não tem compilado dentro.

O paralelo mental de C#: o Expo Go é como rodar um plugin dentro de um host que
alguém publicou na loja — se o host é de uma versão anterior do contrato, o seu
plugin não carrega, e você não controla o host. O dev build é publicar o seu
próprio host. E a assinatura de código da Apple não tem equivalente real em
.NET: não é o Authenticode opcional do Windows — sem ela, **o binário
simplesmente não executa**, e o certificado gratuito expira em 7 dias por design.

---

## Execução — sessão de 2026-09-09 (parte do agente)

A "Divisão do trabalho" acima previu isto: a sessão do agente vai **até a
preparação estar completa** e para. O que segue é o que ficou pronto, com a
evidência de cada afirmação, e o roteiro do que só acontece com o iPhone na mão.

### O ADR que o card exigia antes da implementação

[**ADR-0054**](../adr/0054-o-ambiente-de-execucao-do-ios-e-o-dev-build-local.md)
— *O ambiente de execução do iOS é o dev build local, e o `apiBaseUrl` perde o
default silencioso*. Critérios de `docs/adr/README.md` aplicados, citados
nominalmente no próprio ADR: **6** (contraria o ADR-0002, que elegeu o Expo Go
como estratégia de execução) e **5** (difícil de reverter — muda o fluxo de toda
sessão de mobile). Ele decide o que o ADR-0048 deixou em aberto de propósito:
dev build local × EAS Build × TestFlight, conta gratuita × paga, e o que
acontece com o Simulador.

### O que mudou no código

| Arquivo | O quê | Por quê |
|---|---|---|
| `apps/mobile/src/config.ts` | resolução do `apiBaseUrl` em três degraus (`extra` → host do bundler → **erro alto**) e log de arranque com valor **e origem** | `localhost` num iPhone é o próprio iPhone; e o IP do Mac muda por DHCP |
| `apps/mobile/app.json` | `extra.apiBaseUrl` removido; `ios.bundleIdentifier`; `ios.infoPlist.NSLocalNetworkUsageDescription` | a permissão de rede local do iOS 14+ falha **em silêncio** quando negada |
| `apps/mobile/package.json` | `ios`/`android` → `expo run:*` (o prebuild reescreveu) + `ios:device` | o comando do card vira um script, não um comando a lembrar |
| `packages/api-client/src/cliente.ts`, `index.ts` | `ErroDeRede`, que **nomeia o host tentado**; todo `fetch` do client passa por um envelope | o `fetch` do RN devolve `Network request failed`, sem host |
| `biome.json` | `console.info` permitido; `apps/mobile/{ios,android}` fora do escopo | ver "o gate mordeu", abaixo |
| `apps/mobile/README.md`, skill `voicecoach-cliente` | procedimento do dev build, os 7 dias, o que o Simulador não prova | a mitigação do risco dos 7 dias é documentação, não código |

### Evidência — comandos rodados, saída real

**1. O `prebuild` gera o `Info.plist` a partir do `app.json`** — e é a prova de
que a configuração nativa não precisa ser editada à mão:

```
$ pnpm exec expo prebuild --platform ios --no-install
✔ Created native directory
✔ Finished prebuild

$ plutil -p ios/Voicecoach/Info.plist
  "NSAppTransportSecurity" => {
    "NSAllowsArbitraryLoads" => false
    "NSAllowsLocalNetworking" => true
  }
  "NSLocalNetworkUsageDescription" => "O Voicecoach fala com o servidor de
     desenvolvimento na sua rede local — sem isso, a aula não sai do aparelho."
  "NSMicrophoneUsageDescription" => "O Voicecoach é uma aula de inglês por voz —
     sem microfone não há aula."

$ grep PRODUCT_BUNDLE_IDENTIFIER ios/Voicecoach.xcodeproj/project.pbxproj
  PRODUCT_BUNDLE_IDENTIFIER = "com.luanfiszer.voicecoach";
```

**O achado que não estava no plano:** `NSAllowsArbitraryLoads = false` **com**
`NSAllowsLocalNetworking = true`. Ou seja, o ATS **não** vai bloquear
`http://192.168.x.y:8000` — e não foi preciso afrouxar o ATS para a internet
inteira, que era o risco de resolver isso na base do `NSAllowsArbitraryLoads`.

**2. Falha de rede não nomeia o host** — a premissa do item 7 do ADR, medida em
vez de suposta:

```
$ node -e 'fetch("http://127.0.0.1:59999/v1/turns/x").catch(e => …)'
construtor : TypeError
message    : fetch failed          ← no React Native: "Network request failed"
status     : (não existe)
cause      : ECONNREFUSED | connect ECONNREFUSED 127.0.0.1:59999
host na msg: NÃO
```

**Não há status** porque não houve resposta HTTP: a conexão nem se estabeleceu.
No Node o host ainda aparece em `cause`; no Hermes não há `cause`, e sobra o
texto fixo. Daí `ErroDeRede` morar no client — que é quem montou a URL.

**3. O gate mordeu, e isso é o item 4 do ADR chegando ao CI.** O `prebuild`
criou `apps/mobile/ios/`, e o Biome varre `apps/**`:

```
$ pnpm run lint
apps/mobile/ios/Voicecoach/Images.xcassets/Contents.json format
  × Formatter would have printed the following content
Found 2 errors.
```

Arquivo **gerado** não é código nosso: a pasta saiu do escopo do Biome (ela já
estava no `.gitignore`). Sem isso, todo `pnpm run gates` depois de um build de
aparelho quebraria por arquivo que ninguém escreveu.

**4. Gates, todos verdes** (`backend/` intocado — este card não altera o servidor):

```
$ uv run ruff format --check src tests   → (sem saída: ok)
$ uv run ruff check src tests            → (sem saída: ok)
$ uv run mypy                            → (sem saída: ok)
$ uv run lint-imports                    → Contracts: 4 kept, 0 broken.
$ uv run pytest --cov --cov-fail-under=80
   378 passed, 9 deselected — Total coverage: 93.27%

$ pnpm run gates
   biome check .   → Checked 26 files. No fixes applied.
   tsc --noEmit    → packages/api-client: Done · apps/mobile: Done
```

### Critérios de aceite — situação honesta

| Critério | Situação |
|---|---|
| `apiBaseUrl` efetivo no log de arranque, não `localhost` | **preparado, não verificado**: o log existe (`[config] apiBaseUrl=… (origem: …)`) e o `localhost` deixou de ser possível por default — mas a linha real só sai quando o app subir no aparelho |
| fala real com pico > 0 e transcrição correspondente | **aguarda o aparelho** |
| `p50` de 5 turns, registrado mesmo se estourar 2,4 s | **aguarda o aparelho** |
| gap entre trechos comparado ao do Simulador (< 150 ms) | **aguarda o aparelho** |
| `negada-permanentemente` + `Linking.openSettings()` | **aguarda o aparelho** |
| erro nomeia o host inalcançável | **implementado** (`ErroDeRede`); a verificação com o Mac fora da rede é do roteiro |
| gates verdes, backend inalterado | **verificado** — saída acima |

Nenhum critério foi marcado como cumprido por antecipação. Cinco dos sete só
existem com hardware, o que o próprio card previu na "Divisão do trabalho".

---

## Roteiro — o que fazer com o iPhone na mão

Tempo estimado: ~30 min, dos quais 10–15 são o primeiro build.

### 1. Suba o ambiente (terminal do Mac)

```bash
docker compose up -d
cd backend && uv run alembic upgrade head
uv run uvicorn voicecoach.api.app:create_app --factory --host 0.0.0.0 --port 8000
uv run voicecoach-worker        # em outro terminal: carrega STT (MLX) e TTS (Piper)
curl -s localhost:8000/health/ready     # as quatro dependências têm de estar "up"
```

`--host 0.0.0.0` **não é detalhe**: em `127.0.0.1` o servidor só aceita conexão
do próprio Mac, e o iPhone leva conexão recusada.

### 2. Instale o app (iPhone por cabo, desbloqueado)

```bash
cd apps/mobile && pnpm run ios:device
```

Na primeira vez o build para pedindo assinatura. No Xcode, alvo `Voicecoach` →
`Signing & Capabilities` → *Automatically manage signing*, e escolha o seu Apple
ID em *Team* (`Add an Account…` se não estiver lá). Depois, no iPhone:
*Ajustes → Geral → VPN e Gerenciamento de Dispositivo* → confiar no certificado.

**Anote a data.** O certificado gratuito expira em **7 dias** e o sintoma é o app
não abrir — a tabela para registrar está em `apps/mobile/README.md`.

### 3. Confira o endereço antes de qualquer medição

No log do Metro, no arranque do app:

```
[config] apiBaseUrl=http://192.168.x.y:8000 (origem: bundler)
```

Se aparecer `localhost`, pare: alguém repôs `extra.apiBaseUrl` no `app.json`.
Na primeira requisição o iOS vai pedir **permissão de rede local** — aceite; se
negar, a conexão falha de um jeito que parece backend fora do ar.

### 4. As cinco falas (o número que falta)

Grave **5 turns** pela tela de conversa, falando de verdade, frases de 5–10 s.
A tela mostra os quatro marcos; anote de cada turn:

| Turn | total (`parouDeFalar → primeiroAudivel`) | gaps entre trechos | transcrição bateu? |
|---|---|---|---|
| 1 | | | |
| 2 | | | |
| 3 | | | |
| 4 | | | |
| 5 | | | |

Depois use a rota `/medicao` (10×, insumo fixo) para ter o número comparável ao
do Simulador — os dois medem coisas diferentes de propósito, e a rota está
documentada em `app/medicao.tsx`.

> **Registre o número que der.** O ADR-0048 já estabeleceu que número honesto
> vale mais que número bom; o critério deste card é *medir e registrar*.

### 5. A permissão negada — o caminho que nunca foi exercitado

1. Desinstale o app (zera o TCC) e reinstale.
2. Ao abrir, **negue** o microfone.
3. Toque em gravar de novo: o iOS **não** reapresenta o diálogo — o app deve ir
   para `negada-permanentemente` e mostrar o `OverlayPermissao`.
4. Toque em *Abrir Ajustes*: `Linking.openSettings()` tem de abrir os Ajustes
   **no Voicecoach**, não na raiz.

### 6. O host inalcançável

Com o app aberto, desligue o Wi-Fi do Mac (ou suspenda-o) e tente enviar uma
fala. A mensagem tem de **nomear o endereço**:

```
não foi possível alcançar http://192.168.x.y:8000 (Network request failed)
```

### 7. Traga os números

Cole aqui os resultados; eu registro no card, fecho as pendências do CARD-011 e
do CARD-012 com o que a medição mostrar, e escrevo a dívida do que não fechar.

---

## Regra do explicador — desfecho das perguntas desta sessão

Duas perguntas, ambas feitas **no ponto da decisão**, antes do código:

| # | Pergunta | Quando | Desfecho |
|---|---|---|---|
| 1 | O que o `expo prebuild` faz com um `Info.plist` que já existe? | antes de escrever `expo.ios.infoPlist` no `app.json` | **respondida — "regenera a partir do `app.json`"**, e é o que a execução mostrou: as três chaves do plist gerado vieram todas da config (evidência 1). A nuance que a execução acrescenta: sem `--clean` o prebuild *mescla* sobre o que existe, com o `app.json` tendo precedência — então uma chave escrita à mão pode sobreviver até o primeiro `--clean`, o que é pior que sumir logo, porque some **depois**, sem relação de causa |
| 2 | O que aparece na tela hoje quando o backend está inalcançável? | antes de escrever o `ErroDeRede` | **respondida em parte, corrigida com execução**: "algo genérico" está certo; "com status correto" não — **não há status nenhum** (evidência 2), porque não houve resposta HTTP. Da resposta saiu também o pedido *"ter uma forma de mapear esses erros com facilidade"*, que virou a separação implementada: `ErroDeRede` (sem status, nomeia o host, é diagnóstico) × `ErroDaApi` (Problem Details, é o que o aluno lê) |

Nenhuma pergunta ficou sem desfecho, e nenhuma foi fechada pelo agente com a
própria explicação. Nada entra em `docs/perguntas-em-aberto.md` como pendência.

## Dívidas explícitas

| Dívida | Gatilho / card |
|---|---|
| **Cinco critérios de aceite só existem com o aparelho** (fala real, `p50`, gap, permissão negada, e a verificação do log) | este card, na próxima sessão, com o iPhone na mão |
| **O certificado expira em 7 dias**, sem aviso: o sintoma é o app não abrir | mitigado por documentação (`apps/mobile/README.md`); vira TestFlight quando houver receita (ADR-0054, alternativa C) |
| A copy de aluno para os Problem Details (415, 413, 422, 409, 503…) continua sendo o `title` cru do servidor | **CARD-027** — telas de exceção |
| O `apiBaseUrl` derivado do bundler assume que Metro e backend são a mesma máquina | deixa de valer no **CARD-038** (túnel); o degrau `extra.apiBaseUrl` já existe para isso |
| A fronteira `apps/` ↔ `packages/` continua sem gate automático | dívida antiga, registrada na skill `voicecoach-cliente` |
