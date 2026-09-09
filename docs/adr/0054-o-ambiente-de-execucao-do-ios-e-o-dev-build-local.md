# ADR-0054 — O ambiente de execução do iOS passa a ser o dev build local, e o `apiBaseUrl` deixa de ter default silencioso

- **Status:** aceito
- **Data:** 2026-09-09
- **Relacionado:** [ADR-0002](0002-stack-de-cliente-expo-mais-web-separada.md)
  (Expo Go como estratégia de execução — é a convenção que este ADR contraria),
  [ADR-0048](0048-o-expo-go-da-loja-ficou-para-tras-e-o-aparelho-fisico-vira-divida.md)
  (declarou a dívida e deixou o substituto **em aberto de propósito** — este ADR
  o escolhe), [ADR-0044](0044-dependencias-de-arranque-do-app-expo-e-convivencia-com-pnpm.md)
  (SDK 57 e a régua de dependência), [ADR-0010](0010-politica-de-custo-projeto-pessoal.md)
  (custo zero), CARD-037
- **Critérios de obrigatoriedade** (`docs/adr/README.md`):
  - **6 — contraria uma convenção estabelecida.** O ADR-0002 elegeu
    *"Expo Go/dev build para desenvolvimento"*; na prática o Expo Go era o
    caminho, e o dev build a nota de rodapé. Em iOS a ordem se inverte aqui.
  - **5 — seria difícil de reverter.** Não pelo código (nada no app muda de
    forma), mas pelo **fluxo**: toda sessão de mobile daqui para frente passa a
    depender de um binário assinado que expira, e o Simulador deixa de ser
    testemunha válida de duas classes de comportamento.

## Contexto

O ADR-0048 fechou a Fase 1 com uma dívida escrita: o Expo Go da App Store está
no SDK 54, o projeto no 57, e **um iPhone físico só instala pela App Store** —
então a verificação em aparelho ficou sem canal. A saída (dev build local por
cabo) foi verificada como viável e deliberadamente **não executada**, por escolha
de escopo.

Em 2026-09-09 a dívida foi cobrada por um sintoma, não por um cronograma: o app
"não ouvia o microfone". A investigação mediu, em vez de supor:

| Evidência | Resultado |
|---|---|
| 4 gravações do app no Simulador | duração e formato corretos, **pico = 0, RMS = 0** |
| o mesmo pipeline com áudio gerado por `say` no host | **pico = 25480** — turn `completed` em 4,93 s, transcrição exata, 2 correções |
| `log show` de `tccd` e `SimAudioProcessorService` | **nenhum evento**: o Simulador não chega a abrir o microfone do Mac |
| `Info.plist` do `Simulator.app` e do `SimAudioProcessorService.xpc` | nenhum declara `NSMicrophoneUsageDescription` |

Ou seja: **o produto funciona e o Simulador é que não tem microfone.** O que
faltava nunca foi implementação — era um ambiente de execução capaz de entregar
som de verdade. Três coisas seguem não observadas até hoje: o `p50` em hardware
real, o estado `negada-permanentemente` do iOS, e uma fala humana atravessando o
STT.

Junto com o ambiente vem um segundo problema, que só existe **porque** o app sai
do Mac: hoje `app.json > extra.apiBaseUrl` é `http://localhost:8000`. No
Simulador isso funciona — o Simulador compartilha a pilha de rede do host. Num
iPhone, `localhost` é o **próprio iPhone**, e a falha resultante não se lê como
configuração errada.

## Decisão

**Em iOS, o ambiente de execução do cliente passa a ser o dev build local,
assinado com Apple ID gratuito e instalado por cabo. E o `apiBaseUrl` deixa de
ter default silencioso: ele é derivado do host do bundler, com `extra` como
override explícito e erro alto quando nenhum dos dois resolve.**

1. **`npx expo run:ios --device`**, com conta Apple **gratuita**. Custo R$ 0
   (ADR-0010 preservado); o preço é a validade de **7 dias** do certificado e a
   reinstalação por cabo. O procedimento e a data de expiração ficam no
   `apps/mobile/README.md` — o sintoma de um certificado vencido é o app
   simplesmente não abrir, que é impossível de diagnosticar sem o registro.
2. **O SDK 57 fica** (ADR-0044/0048). Este ADR muda o canal, não a versão.
3. **O Simulador continua sendo o ambiente do dia a dia** para UI, navegação,
   estado e caminho triste — é mais rápido e não expira. Ele **deixa de valer**
   para exatamente três coisas, e isso é regra, não recomendação:
   - qualquer número de **latência** (ADR-0048: compartilha CPU, rede e disco do Mac);
   - qualquer coisa que dependa do **microfone** (ele grava silêncio digital);
   - o estado **`negada-permanentemente`** de permissão.
4. **A pasta `ios/` não é versionada** (já está no `.gitignore` do app, agora com
   motivo escrito): a configuração nativa é *gerada* a partir do `app.json`
   (Continuous Native Generation). Consequência operacional que morde: **editar
   `Info.plist` à mão é trabalho que o próximo `prebuild` apaga** — o que
   precisar entrar no plist entra em `expo.ios.infoPlist`.
5. **`NSLocalNetworkUsageDescription` passa a ser declarado.** A partir do
   iOS 14, falar com um IP da LAN dispara a permissão de rede local; sem o texto,
   o prompt aparece vazio, e uma negação faz a conexão falhar de um jeito que se
   disfarça de "backend fora do ar".
6. **A resolução do `apiBaseUrl` tem três degraus, nesta ordem:**
   1. `extra.apiBaseUrl`, quando presente — **override explícito**, que é o que
      o CARD-038 vai usar quando o backend sair da LAN;
   2. **o host de onde o JavaScript veio**, com a porta da API — no aparelho,
      esse host **já é o IP do Mac na LAN**, porque o Metro e o backend são a
      mesma máquina;
   3. nada resolveu ⇒ **erro alto no import**, dizendo o que configurar.
   O valor efetivo e a **origem** dele são registrados no log de arranque.

   > **Correção feita na própria sessão, com o aparelho na mão.** A primeira
   > versão deste item dizia "o host do bundler (`Constants.expoConfig.hostUri`)".
   > **`hostUri` é `undefined` num dev build**: ele vem do *manifesto* que o Expo
   > CLI entrega ao Expo Go, e um dev build não tem manifesto — o app é o próprio
   > host. O que existe nos dois ambientes é `SourceCode.scriptURL`, a URL de
   > onde o bundle foi carregado, e é dela que o host é extraído (`hostUri`
   > continua sendo tentado primeiro, para o Expo Go). Quem revelou isso foi o
   > erro alto do degrau 3, disparando na primeira abertura no iPhone: a decisão
   > de falhar barulhento se pagou antes de o card fechar.
7. **Falha de rede nomeia o host.** O client passa a envolver a falha de
   transporte num `ErroDeRede` que carrega a `baseUrl` tentada. O `fetch` do
   React Native devolve `TypeError: Network request failed` — sem host, sem
   porta, sem causa —, e esse é justamente o erro que o aluno (e o desenvolvedor)
   vai ver quando o IP mudar por DHCP ou o Mac dormir.

## Alternativas consideradas

### Alternativa A — Continuar no Simulador e declarar a dívida de novo

- **O que é:** manter o ADR-0048 como está, adiando o aparelho mais uma fase.
- **A favor:** custo zero de sessão, nada expira.
- **Por que foi rejeitada:** a dívida deixou de ser sobre um número faltando e
  passou a ser sobre **uma classe inteira de comportamento não observável**. O
  Simulador não grava som — provado nesta sessão, não suposto. Continuar nele é
  escolher não saber, e o CARD-011 e o CARD-012 ficariam com pendências que
  nenhum trabalho futuro poderia fechar.

### Alternativa B — EAS Build (build na nuvem do Expo)

- **O que é:** `eas build --profile development --platform ios`, com o Expo
  compilando e assinando por você e o app instalado por link.
- **A favor:** não exige Xcode local nem entender assinatura; o build sai de uma
  máquina limpa, o que elimina "funciona na minha máquina".
- **Por que foi rejeitada:** (1) a assinatura *pelo ar* para um aparelho
  registrado exige **Apple Developer Program** (US$ 99/ano) — sem ele o EAS
  também cai no fluxo de conta gratuita, que instala por cabo do mesmo jeito;
  (2) a fila gratuita do EAS é uma dependência de serviço externo para um passo
  que a máquina local faz em ~10–15 min, e o ADR-0010 trata dependência de conta
  como custo mesmo quando o preço é zero. **Fica como plano B escrito**: se o
  build local travar, `eas build --local` compila com a mesma toolchain sem
  mudar a conta.

### Alternativa C — TestFlight com Apple Developer Program

- **O que é:** US$ 99/ano, build interno distribuído pela Apple, validade de
  **90 dias** em vez de 7, instalação pelo ar, sem cabo.
- **Por que foi rejeitada:** contraria o ADR-0010 frontalmente. É a escolha
  certa quando existir um terceiro instalando o app sem cabo — o mesmo gatilho já
  registrado no ADR-0048 e na Parte E da visão (Fase 4, sob receita).

### Alternativa D — Baixar o projeto para o SDK 54, para caber no Expo Go da loja

- **O que é:** a Alternativa B do ADR-0048.
- **Por que continua rejeitada:** ela pina o ritmo do projeto ao da App Store
  (onze meses sem publicar) e invalida duas medições específicas do RN 0.86 —
  o `fetch` global entregando `response.body` em pedaços (ADR-0044) e o
  `FormData` que só aceita `Blob` (ADR-0046 §4). E, decisivo agora: **não
  resolveria o microfone**, porque o problema nunca foi o Expo Go, foi o
  Simulador.

### Sub-decisão: por que derivar do `hostUri` em vez de fixar o IP no `app.json`

- **O que seria:** trocar `http://localhost:8000` por `http://192.168.x.y:8000`
  no `extra` e seguir a vida.
- **Por que foi rejeitada:** o IP do Mac muda por DHCP, e o sintoma é o app parar
  de funcionar sem nada ter mudado no código — uma sessão inteira perdida
  procurando bug onde há configuração vencida. Derivar do `hostUri` neutraliza
  isso na origem: **se o Metro alcança o aparelho, o backend também alcança**,
  porque são a mesma máquina. O override continua existindo para quando isso
  deixar de ser verdade (CARD-038, backend atrás de túnel).
- **O que se paga:** `hostUri` só existe em desenvolvimento com o Expo CLI. Num
  build de produção ele é `undefined` — e por isso o terceiro degrau é erro alto,
  e não `localhost` de novo. Um app de produção sem `extra.apiBaseUrl` **não
  sobe**, o que é o comportamento correto: falhar no arranque é melhor que falhar
  no meio da primeira gravação do aluno.

## Consequências

**Positivas**

- **Três critérios de aceite parados voltam a ser alcançáveis**: o `p50` em
  hardware real (CARD-012), o `negada-permanentemente` (CARD-011) e a primeira
  fala humana a atravessar o produto.
- O app deixa de depender de um **host que alguém publicou na loja**: os módulos
  nativos passam a ser os que o `package.json` pede, e a incompatibilidade de SDK
  do ADR-0048 deixa de existir por construção.
- **Configuração errada vira erro legível**: `localhost` num aparelho passa a ser
  impossível por default, e falha de rede passa a nomear o host.

**Negativas — o preço aceito**

- **O certificado expira em 7 dias.** Sem aviso, sem mensagem: o app não abre. A
  mitigação é documentação, não código.
- **Toda sessão de mobile ganha um passo**: quando o aparelho for necessário, é
  cabo, Xcode e ~10–15 min de build inicial. O Simulador continua para o resto —
  mas a escolha entre os dois passa a ser uma decisão consciente por tarefa.
- **`hostUri` é uma API do ambiente de desenvolvimento**, e o app agora depende
  dela para o caminho feliz. Se o Expo mudar essa forma num SDK futuro, o sintoma
  é o erro alto do terceiro degrau — barulhento, e não silencioso, que é o
  motivo de ele existir.
- **Uma configuração nativa a mais para lembrar** (`NSLocalNetworkUsageDescription`),
  num arquivo que ninguém edita diretamente porque é gerado.

## O que só o aparelho revelou (sessão de 2026-09-09)

Cada item abaixo é a tese deste ADR se pagando — e **nenhum deles era visível no
Simulador**, porque lá nada disso é compilado, assinado ou roteado:

| Achado | Por que ficou invisível até aqui |
|---|---|
| **`expo-modules-core` não compila contra `react-native-worklets@0.12`** (`no member named 'executeSync'`) | o `peerDependencies` pede `^0.7.4…^0.10.0`, o `expo-router` puxa `0.12.1` via `@expo/ui`, e o pnpm só **avisa**. No Simulador o `expo-modules-core` vinha pré-compilado dentro do cliente Expo: **ninguém nunca tinha compilado esse arquivo**. Resolvido alinhando o SDK (`expo install --fix`), cuja `57.0.17` já usa `runSync` |
| **Três frameworks pré-compilados são embutidos sem assinatura** (`hermesvm`, `ReactNativeDependencies`, `ExpoModulesJSI`) | `Build Succeeded`, e o iOS recusa na instalação: `ApplicationVerificationFailed`. Assinatura de código não existe no Simulador |
| **O iPhone recusa app de desenvolvimento com o Modo de Desenvolvedor desligado** | conceito que só existe em hardware; o sintoma no `xcodebuild` é um timeout de destino, não um erro de permissão |
| **`Constants.expoConfig.hostUri` é `undefined` no dev build** | ver a correção do item 6 |
| **A URL assinada da mídia apontava para `localhost:9000`** | no Simulador `localhost` é o Mac. No iPhone é o iPhone — o áudio simplesmente não toca. A saída já estava decidida (ADR-0045, `S3_PUBLIC_ENDPOINT_URL`), e **reescrever o host no cliente daria 403**, porque ele entra no SigV4 |
| **O DHCP trocou o IP do Mac no meio da sessão** (`.98` → `.99`) | o app se ajustou sozinho (item 6); a configuração do storage, não. Por isso ela passou a usar o **nome mDNS** (`<host>.local`) em vez do IP |

**Equivalente mental .NET:** o Expo Go é rodar seu plugin dentro de um host que
*outra pessoa* publicou — se o host é de uma versão anterior do contrato, seu
plugin não carrega e você não controla o host. O dev build é publicar o seu
próprio host. E a assinatura de código da Apple não tem paralelo real: não é o
Authenticode opcional do Windows, onde o binário roda sem assinatura com um
aviso. Aqui, **sem assinatura o processo não inicia** — e o certificado gratuito
tem 7 dias de validade por design, não por engano.
