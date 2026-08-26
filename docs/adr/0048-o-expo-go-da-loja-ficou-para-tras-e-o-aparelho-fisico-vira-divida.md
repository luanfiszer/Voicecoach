# ADR-0048 — O Expo Go da App Store ficou 3 SDKs para trás, e o aparelho físico vira dívida declarada

- **Status:** aceito
- **Data:** 2026-08-26
- **Relacionado:** [ADR-0002](0002-stack-de-cliente-expo-mais-web-separada.md)
  (Expo Go como estratégia de execução), [ADR-0044](0044-dependencias-de-arranque-do-app-expo-e-convivencia-com-pnpm.md)
  (SDK 57 escolhido com medição), [ADR-0010](0010-politica-de-custo-projeto-pessoal.md)
  (custo zero), CARD-011, CARD-012
- **Critérios de obrigatoriedade** (`docs/adr/README.md`): **6 — contraria uma
  convenção estabelecida.** O ADR-0002 assumiu, sem dizer com todas as letras,
  que o Expo Go cobriria **também** o teste em aparelho físico. Ele não cobre, e
  a consequência é um critério de aceite que deixa de ser alcançável pelo caminho
  previsto. Registrar a exceção é a própria regra do critério 6.

## Contexto

O CARD-012 tem como critério de saída da Fase 1 um número medido **em aparelho
físico**: do envio da fala até a primeira palavra sair do alto-falante. O plano
sempre foi o do ADR-0002 — Expo Go, sem dev build, custo zero.

Ao tentar abrir o projeto no iPhone, o Expo Go respondeu *"projeto incompatível"*.
A investigação, feita contra a API da Apple em quatro lojas (BR, US, GB, JP):

| | |
|---|---|
| Expo Go na App Store | **54.0.2**, publicado em **2025-09-23** |
| SDK que ele suporta | **54** |
| SDK do projeto | **57** (ADR-0044) |
| Expo Go que roda SDK 57 | **57.0.9** — existe, mas **não na App Store** |

O Simulador funciona porque o Expo CLI baixa o build 57.0.9 direto dos servidores
do Expo. **Um iPhone físico só instala pela App Store**, e lá não há build mais
novo para atualizar. Não é aparelho velho, não é download errado, não é cache: é
o canal de distribuição parado há onze meses.

## Decisão

**O projeto permanece no SDK 57. A verificação em aparelho físico iOS deixa de
ser feita por Expo Go e vira dívida declarada, com o motivo escrito. A Fase 1
fecha com o número do Simulador, e o número do aparelho é card próprio.**

1. **O SDK 57 fica.** As escolhas do ADR-0044 foram medidas nele, e a medição do
   CARD-012 (p50 2,47 s, gap 143 ms) é dele.
2. **O Simulador é o ambiente de verificação corrente**, com a limitação escrita
   em todo número que sair dele: compartilha CPU, rede e disco do Mac.
3. **A dívida é nomeada, não omitida.** Três critérios continuam abertos e
   **assim declarados** no CARD-012: o p50 em aparelho, a permissão negada
   permanentemente (herdada do CARD-011), e o comportamento de rede móvel.
4. **O caminho de saída existe e está documentado**: `npx expo run:ios --device`
   com Xcode e Apple ID gratuita — **verificado como viável nesta máquina**
   (Xcode 26.6, CocoaPods 1.16.2, iPhone já pareado). Custa R$ 0; o app expira em
   7 dias. Não foi executado por escolha de escopo, não por impedimento.
5. **Gatilho para reavaliar:** o Expo Go da App Store publicar suporte ao SDK do
   projeto, **ou** o primeiro critério que só o aparelho prove virar bloqueio de
   release (permissão, push, áudio em rede móvel, publicação na loja).

## Alternativas consideradas

### Alternativa A — Dev build local por cabo

- **O que é:** `npx expo run:ios --device`; um cliente de desenvolvimento
  instalado direto no iPhone, com assinatura de conta Apple gratuita.
- **A favor:** resolve **hoje**, no SDK 57, com o código já medido, e a
  infraestrutura toda já existe nesta máquina. Custo zero (ADR-0010 preservado).
- **Por que não agora:** exige configuração interativa de assinatura no Xcode,
  ~10–15 min de build inicial, e reinstalação a cada 7 dias. **Decisão de escopo
  do desenvolvedor**, tomada com a alternativa na mesa: seguir verificando no Mac.
  **É a saída preferencial quando a dívida for cobrada** — não uma ideia nova a
  ser redescoberta.

### Alternativa B — Baixar o projeto para o SDK 54

- **O que é:** `expo@~54`, `react-native@0.81.5`, `expo-audio@~1.1.1` e o resto
  da tabela do SDK 54, para caber no Expo Go da loja.
- **A favor:** investigado a fundo, e **mais viável do que parecia**: o
  `expo-audio@1.1.1` tem `createAudioPlayer`, `AudioPlayerOptions.updateInterval`,
  `useAudioRecorder` e `useAudioRecorderState` — ou seja, a fila do ADR-0047 e a
  gravação do CARD-011 **não precisariam ser reescritas**.
- **Por que foi rejeitada:** não é um passo temporário, é **pinar o ritmo do
  projeto ao da App Store**, que ficou onze meses sem publicar. E invalida duas
  medições desta sessão que são específicas do RN 0.86: o `fetch` global
  entregando `response.body` em pedaços (ADR-0044) e o `FormData` que só aceita
  `Blob` (ADR-0046 §4) — as duas teriam de ser refeitas em 0.81, com resultado
  desconhecido. Trocar arquitetura medida por arquitetura a remedir, para
  resolver uma verificação, é caro na direção errada.

### Alternativa C — TestFlight

- **O que é:** distribuir um build interno pela Apple.
- **Por que foi rejeitada:** exige Apple Developer Program (US$ 99/ano), o que
  contraria o ADR-0010 frontalmente. Fica registrada como o caminho quando
  houver receita (Fase 4) — é o mesmo gatilho da publicação na loja.

## Consequências

**Positivas**

- O motivo da dívida fica **auditável**: quem ler o CARD-012 daqui a três meses
  não vai supor desleixo nem repetir a investigação das quatro lojas.
- A saída está escolhida e verificada de antemão (Alternativa A), então cobrar a
  dívida é executar um comando, não reabrir uma decisão.
- O SDK 57 e as medições do CARD-012 continuam válidos e comparáveis.

**Negativas — o preço aceito**

- **Três critérios de aceite ficam abertos**, e um deles é o **critério de saída
  da Fase 1**. A fase fecha com uma ressalva escrita, não limpa.
- **A classe de bug que só aparece em aparelho continua invisível:** permissão
  negada permanentemente, comportamento em rede móvel, ATS do iOS contra HTTP em
  claro, e desempenho real de CPU e decodificação de áudio. O número de 2,47 s é
  de um Simulador com os recursos de um Mac.
- **A distância só cresce.** Cada SDK novo afasta mais o projeto do Expo Go da
  loja, e o custo de voltar para lá (Alternativa B) sobe com o tempo.
- **O ADR-0002 fica parcialmente desatualizado** em premissa — ele segue correto
  na escolha (Expo + RN + monorepo), mas a frase "Expo Go/dev build para
  desenvolvimento" esconde que, para iOS físico, hoje só a segunda metade vale.

**Equivalente mental .NET:** é a diferença entre depurar no IIS Express e depurar
no servidor de verdade. Tudo funciona no primeiro, e a classe de problema que só
existe no segundo continua lá, esperando — com a agravante de que aqui o
"servidor de verdade" também é onde o usuário vive.
