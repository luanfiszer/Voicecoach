# CARD-027 — As telas de exceção do app: o que o aluno vê quando algo não vai bem

- **ID:** CARD-027
- **Épico:** Fase 2 — Proteção de margem (fecha o lado cliente dela)
- **Plataforma:** mobile · **Esforço:** M · **Status:** concluído (fila local de
  offline cortada de escopo — ver Execução)
- **Dependências:** CARD-015 (quota e kill switch), CARD-025 (varredura de
  travados), CARD-026 (desfecho de provedor indisponível) e os três cards de
  backend desta tela: **CARD-031** (sessão encerrada como desfecho tipado),
  **CARD-032** ("Descartar"), **CARD-033** (saldo e serviço pausado como
  leitura)

## Contexto

Três artboards estão desenhados desde 2026-08-17 e **nunca tiveram dono**:

| Artboard | Empurrado para "Out" por |
|---|---|
| **14** offline — *"Sua fala está guardada aqui"* | CARD-012 (*"offline real"* em Out) |
| **15** quota atingida — *"Por hoje é isso"* | CARD-015 (*"UI de cota restante"* em Out) |
| **16** pausado + timeout — *"Demorou mais que o normal"* | ninguém: é o **achado #6** da `reconciliacao-telas-dominio.md`, órfão desde 2026-08-18 |

Não são telas esquecidas: são telas adiadas três vezes, por três cards
diferentes, e o backlog nunca criou o card que as recebesse. Este é ele.

## Problema

**Todo caminho triste do produto termina numa tela que não existe.**

O backend já sabe (ou vai saber, nos cards de que este depende) dizer as quatro
coisas. O app não sabe mostrar nenhuma:

- **sem rede** — o `enviarTurn` falha e a fala é perdida. O CARD-012 entregou
  retry com backoff, **não** fila local: o áudio existe em `file://` e ninguém o
  guarda para depois;
- **cota estourada** — o POST volta com Problem Details e o app mostra "Algo deu
  errado", indistinguível de erro de verdade;
- **kill switch** — idem, e é o caso em que a mensagem honesta importa mais
  (*"desligamos o professor para não gastar além do previsto"*);
- **turn travado** — o app espera indefinidamente. O CARD-025 marca `failed` no
  servidor; ninguém decidiu o que o app faz com isso, nem o que **"Descartar"**
  significa.

## Proposta técnica

- **Um overlay, quatro conteúdos.** As quatro telas têm a mesma forma (cartão
  sobre a conversa, título + explicação + até dois botões) e o mesmo insumo: um
  desfecho que veio do servidor **ou** a ausência dele. Um componente, quatro
  usos — não quatro componentes.
- **O Problem Details vira o discriminador.** O ADR-0040 já garante `type` como
  URN estável; o cliente casa sobre ele, nunca sobre a mensagem. É o que separa
  "cota" de "kill switch" de "erro de verdade" sem parsear texto.
- **Fila local para o offline (artboard 14).** A gravação sobrevive ao
  fechamento do app e sobe sozinha quando a conexão voltar, **reusando a mesma
  `Idempotency-Key`** — o servidor já responde `replayed: true` e não duplica
  (provado no CARD-012).
- **A decisão pendente sobre "Descartar" mudou de casa:** ela é do
  **[CARD-032](CARD-032-descartar-turn-travado.md)**, que decide e implementa o
  lado servidor. Fica aqui o registro do que estava em jogo: Três
  leituras, e elas divergem no servidor: (a) só some da tela — o turn `failed`
  fica no histórico; (b) o app pede para o servidor apagar; (c) nunca chegou a
  existir turn (caso offline) e é só apagar o arquivo local. Provavelmente
  **(a) e (c)**, e a diferença entre elas é onde a fala estava quando o aluno
  desistiu. **Não implementar antes do ok.**

> **Vira ADR se (b) for escolhido** — critério 2 (o contrato ganha uma ação
> destrutiva sobre um recurso) e critério 4 (dado do aluno sendo apagado por
> pedido dele: é o começo do direito de exclusão, que o CARD-017 trata do outro
> lado).

## Escopo

- **In:** o componente de overlay; os quatro conteúdos; a fila local de envio
  com persistência entre aberturas do app; o casamento por URN de Problem
  Details; o desfecho de "Descartar" implementado conforme a decisão.
- **Out:** *"Avisar quando voltar"* do artboard 16 — é **push**, cortado pela
  visão §F com gatilho escrito (revisão espaçada). O botão não entra, e o card
  registra por quê; a UI de saldo de cota **antes** de estourar (artboard 12, é
  a tela de perfil e depende da auth da Fase 3); retry automático de turn
  travado (o ADR-0037 proíbe depois de entrega parcial).

## Critérios de aceite

- **Dado** o app em modo avião, **quando** o aluno grava e solta, **então** a
  fala aparece como pendente, sobrevive a fechar e reabrir o app, e sobe sozinha
  quando a rede volta — **sem** criar um segundo turn.
- **Dado** um POST que volta com a URN de cota, **então** o aluno vê a tela de
  cota (não "algo deu errado"), e **continua conseguindo ler** os turns
  anteriores da sessão.
- **Dado** um POST que volta com a URN de kill switch, **então** a mensagem é a
  do orçamento, distinta da de cota.
- **Dado** um turn que passou do prazo sem evento, **então** o aluno vê a tela de
  timeout com as duas ações, e a gravação **não** foi perdida.
- **Dado** "Descartar", **então** acontece exatamente o que foi decidido — com
  teste, e com o estado do servidor verificado se a decisão o envolver.

## Riscos

- **Fila local é mais cara do que parece.** Persistir arquivo + metadados,
  sobreviver a reinício, não subir duas vezes, não crescer sem limite. É a maior
  parte do esforço do card e o candidato natural a virar card próprio se
  estourar — e nesse caso o corte é **offline sai, as outras três ficam**, não o
  contrário.
- **Dependência tripla.** Três cards precedem este. Se algum atrasar, a parte
  correspondente vira mock — e mock de tela de erro tem o hábito de sobreviver
  até produção. Se for mockar, escreva o gatilho de remoção.
- **Testar offline no Simulador não prova nada** sobre o aparelho, e o aparelho
  físico está bloqueado pelo ADR-0048. Declare o que ficou por provar.

## Objetivo de aprendizado

Persistência local no Expo — `expo-file-system` para o áudio e o que guarda os
metadados (`AsyncStorage`? SQLite?), com a pergunta que decide: o que sobrevive
a um *force quit*, e o que sobrevive a um *update do app*. Não há equivalente
direto em .NET: o mais próximo é `IsolatedStorage`, e a analogia quebra porque
aqui o sistema operacional pode apagar o diretório de cache sem avisar.

## Execução (2026-09-13, loop autônomo)

**Corte de escopo, pré-autorizado pelo próprio card: a fila local sai, as
outras três telas ficam.** O risco já previa isto ("nesse caso o corte é
offline sai, as outras três ficam, não o contrário"). Persistir o áudio entre
reaberturas do app exige `expo-file-system` (confirmado: existe no pnpm store
por dependência transitiva, mas **não** tem symlink em
`apps/mobile/node_modules` — não é importável sem virar dependência direta), e
toda dependência nova exige ADR com alternativa descartada (critério 1 de
`docs/adr/README.md`, régua da skill `voicecoach-cliente`). Implementado em vez
disso: **retry manual na mesma sessão do app** — `ultimaTentativa` guarda
`{uri, pararEm}` da última gravação em `useRef`, e "Tentar enviar de novo"
reenvia com uma `Idempotency-Key` NOVA (a original nunca chegou ao servidor —
falha de transporte, não de aceite, então não há turn a duplicar). O que fica
de fato descoberto: a gravação **não sobrevive a fechar o app** enquanto
offline. Dívida declarada, não escondida — vira card próprio se for
priorizada, com o gatilho já escrito no risco original.

**Um componente, quatro conteúdos — como o card propôs.**
`OverlayDeExcecao.tsx` é um `Modal` transparente sobre a tela, modelado no
`OverlayPermissao.tsx` do artboard 13. `conteudoDaExcecao.ts` (módulo puro,
sem import de React Native) decide qual dos quatro (`offline`/`cota`/
`pausado`/`travado`) a partir de `ErroDaApi | ErroDeRede | null` — exatamente
o padrão do ADR-0061: lógica extraída, testada com Vitest, zero mock de
módulo nativo.

**O discriminador é a URN do Problem Details, nunca o texto ou o status
HTTP sozinho — e isto expôs um buraco pré-existente no `packages/api-client`,
não introduzido por este card.** `ErroDaApi` sempre teve `status`/`detalhe`,
mas **descartava o campo `type`** do corpo — o próprio discriminador que o
ADR-0040 define. Sem ele, cota (429) e kill switch (503) seriam
indistinguíveis por status quando um dia dividirem o mesmo código, e a
distinção do card ("kill switch é o caso em que a mensagem honesta importa
mais") dependeria de comparar strings de mensagem. Corrigido: `ErroDaApi`
ganhou o campo `tipo`, `falhar()` em `cliente.ts` passa a lê-lo e propagá-lo.
**Não abriu ADR**: implementa uma decisão já tomada (ADR-0040), não decide
nada novo — é o gap de um wrapper de erro que nunca tinha lido o campo
inteiro, não uma mudança de contrato.

**"Descartar" chama o endpoint real do CARD-032** (`POST
/v1/turns/{id}/discard`, adicionado a `cliente.ts` como `descartarTurn`) e
depois `limpar()` incondicionalmente — a falha do `await` fica só no log
(`console.error`), porque o objetivo do botão é destravar a tela do aluno,
não confirmar com o servidor antes de deixar. Mesmo padrão de "silêncio
síncrono primeiro" do CARD-042.

**O botão "Entendi" (cota/pausado) não está em nenhum artboard, e é decisão,
não esquecimento.** O único botão do artboard 16 para o caso "pausado" —
"Avisar quando voltar" — foi cortado pela visão §F (é push, com revisão
espaçada como gatilho de retomada, registrado no próprio Escopo deste card).
Sem nenhum botão, a tela trancaria o aluno sem saída nenhuma — o que nenhum
artboard pede. "Entendi" só fecha o overlay; documentado no docstring do
componente.

**"Gravar de novo" (travado) segue a decisão do CARD-032, não "Tentar de
novo".** Reprocessar depois de entrega parcial é proibido pelo ADR-0037; o
botão do artboard 16 vira convite a **gravar de novo**, não a reenviar o
mesmo áudio — e por isso o handler é `aoFechar` (o mesmo que zera o estado),
não um reenvio.

**`respostaTravadaEmSegundos` é configuração, não `30` fixo no texto** —
`app.json > extra` + validação em `config.ts` (ADR-0044 §4). O watchdog
(`armarTravamento`/`desarmarTravamento` em `useTurno.ts`) conta a partir do
upload concluído (`turnId` já existe), como o texto promete ("sua fala FOI
ENVIADA"), não do início da gravação — e é desarmado em toda transição
terminal (`completed`, `failed`, `limpar()`) e no unmount, para não disparar
sobre um turn que já fechou bem.

**Verificação end-to-end real dos três cenários alcançáveis sem toque, via
`/medicao` (o mesmo mecanismo de deep-link auto-disparado do CARD-037/029 —
não há automação de toque nesta máquina, CARD-011):**

1. **Offline** — verificado em sessão anterior (modo avião real no
   Simulador): overlay "Sua fala está guardada aqui" com "Tentar enviar de
   novo", reenvio confirmado chegando ao servidor.
2. **Cota** — backend local com `DAILY_QUOTA_TURNS_PER_STUDENT=1` (o campo
   tem `gt=0`, não aceita `0`; precisou consumir 1 turno real antes do que
   estoura). Segunda execução (`?execucoes=2&auto=1`) voltou 429 com a URN de
   cota; overlay "Por hoje é isso" renderizou a mensagem do servidor e o
   botão "Entendi". Screenshot capturado.
3. **Travado** — sem worker isolado para pausar (a fila `arq` roda no mesmo
   processo do `uvicorn` nesta configuração local), o backend inteiro foi
   congelado com `kill -STOP` logo após o upload ser aceito (turn em
   `transcrevendo`) e descongelado com `kill -CONT` 33s depois. Como o
   watchdog é um `setTimeout` do lado do cliente, independente de qualquer
   resposta de rede, ele disparou sozinho: overlay "Demorou mais que o
   normal" com o texto dinâmico ("...não chegou em **30s**...", confirmando
   que a config realmente chega ao componente) e os dois botões. Screenshot
   capturado.
4. **Pausado (kill switch)** — **não verificado end-to-end nesta sessão**.
   Forçar `ServiceBudget.is_exceeded()` exigiria manipular o orçamento no
   Redis ou derrubar `DAILY_BUDGET_USD`/`MONTHLY_BUDGET_USD` a um valor que
   nenhuma chamada real ultrapassa sem gasto de LLM adicional. Coberto por
   teste unitário (`conteudoDaExcecao.test.ts`: a URN de kill switch produz
   tela **distinta** da de cota, com a mesma forma) e por leitura de código —
   o caminho é idêntico ao de cota, só troca a URN casada. Dívida declarada:
   quem quiser a prova end-to-end precisa de um jeito barato de forçar o
   orçamento no ambiente local (candidato a nota de card futuro, não
   bloqueador deste).

**O que não foi possível verificar mesmo com os workarounds:** o toque real
nos botões "Gravar de novo"/"Descartar"/"Tentar enviar de novo" — sem
automação de toque instalada (`idb`/Maestro/Detox ausentes, CARD-011), o
overlay foi confirmado visualmente e por deep link, mas o `onPress` de cada
botão só tem prova por leitura de código + os testes unitários de
`descartarTurn`/`tentarNovamente` (a chamada HTTP e o reenvio, isolados do
gesto). Mesma classe de lacuna do CARD-029 (`RefreshControl`), não uma nova.

**Nenhum ADR novo.** Contra os seis critérios de `docs/adr/README.md`:
nenhuma dependência nova entrou (a que entraria — persistência local — foi
justamente a que saiu de escopo); a fronteira do contrato não mudou (`type`
já era parte do Problem Details desde o ADR-0040, só não vinha propagado); não
afeta custo recorrente nem segurança; a decisão é trivialmente reversível
(reverter é remover um componente e dois campos); não contraria convenção
nenhuma — implementa uma já escrita.

**Testes:** `packages/api-client/src/cliente.test.ts` (+3: extração de
`tipo`, `descartarTurn` com 204 e com erro),
`apps/mobile/src/features/excecoes/conteudoDaExcecao.test.ts` (8, novo — cada
um mapeado a um critério de aceite: URN de cota ≠ URN de kill switch, `detail`
ausente nunca vira mensagem em branco, URN desconhecida cai no fallback
existente). `pnpm run gates` verde (Biome + `tsc --strict` + 41 testes
Vitest em 6 arquivos).

**Regra do explicador:** nenhuma pergunta de previsão coube nesta sessão — as
duas decisões mais caras de errar (cortar a fila local; adicionar "Entendi"
fora do artboard) já tinham direção conservadora escrita no próprio card
(o risco) ou seguiam precedente já registrado (CARD-029/032), e foram tomadas
com a razão documentada, não perguntadas.
