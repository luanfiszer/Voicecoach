# CARD-042 — Regravar cala o professor: o bug do playback que sobrevive ao `limpar()`

- **ID:** CARD-042
- **Épico:** Qualidade da conversa (briefing 2026-09-09, ponto 2 — lado do cliente)
- **Esforço:** P
- **Status:** parcial (2026-09-11) — causa confirmada e corrigida; a medição no aparelho é dívida
- **Dependências:** CARD-037 (o app tem de estar no aparelho), ADR-0047

## Contexto

Segundo apontamento do primeiro uso real: *ao errar a gravação e tentar
recomeçar, o app continua falando*.

**A investigação de 2026-09-09 encontrou o oposto do que o briefing supunha.** O
briefing tratava isto como feature a construir ("as peças existem"). Elas não
só existem: **já estão ligadas**.

```
TelaConversa.tsx:86     turno.limpar();  void gravacao.iniciar();
useTurno.ts:210-212     limpar → cancelar() → abortador.current?.abort()
                                → fila.limpar()
useFilaDePlayback.ts:110  soltarTudo → for (player of players) player.remove()
```

Logo: **débito técnico, não de negócio.** A regra está certa e escrita no
código; a implementação não a cumpre. Isto é um bug, e por isso **não gera
ADR** — o que ele gera, se a causa confirmar a hipótese, é um `learnings/`.

## Problema

`soltarTudo()` chama `player.remove()` **sem `player.pause()` antes**. Hipótese
principal: o `remove()` do `expo-audio` libera o objeto compartilhado, mas o
áudio já entregue ao `AVPlayer` do iOS continua saindo até o buffer esvaziar —
e o aluno ouve o professor por cima da própria gravação.

**A hipótese não está confirmada.** Ela vem da leitura do código e do
comportamento relatado; o Simulador nunca a mostrou, e o CARD-037 já ensinou que
o aparelho cobra o que o Simulador esconde. Uma segunda hipótese sobrevive e
precisa ser eliminada junto: `useGravacao.iniciar()` chama
`setAudioModeAsync({ allowsRecording: true })`, e a mudança de categoria da
sessão de áudio do iOS pode interagir com um player em voo de formas que só o
aparelho revela.

**Este card começa reproduzindo, não corrigindo.**

## Proposta técnica

1. **Reproduzir no iPhone e registrar o que acontece**, com log dos instantes:
   dedo no botão → `limpar()` → `remove()` → último som audível. Sem esse
   número, a correção é chute e a verificação é opinião.
2. **`pause()` antes de `remove()`** em `soltarTudo()`, e `pause()` no player em
   reprodução antes de percorrer o mapa — a ordem importa: silenciar o que toca
   primeiro, liberar depois.
3. **Silenciar não pode depender de rede.** A ordem em `TelaConversa` passa a
   ser explícita: calar primeiro, e só então iniciar a gravação (que é
   assíncrona e pede permissão). Hoje `limpar()` já vem antes, mas por
   coincidência de escrita, não por invariante testada.
4. Se a hipótese cair, a segunda linha de investigação é a sessão de áudio —
   e a saída provável é ordenar `setAudioModeAsync` **depois** do silêncio.
5. O `AbortController` já cancela a conexão viva e **isso está correto**: o
   servidor continuar é o comportamento de hoje, e o CARD-043 é quem muda isso.

## Refinamento obrigatório — cache e limites

**Cache:** não se aplica.

**Endpoint:** não se aplica — nenhum endpoint é tocado. (O aviso ao servidor é o
CARD-043, deliberadamente separado: silenciar tem de funcionar mesmo offline.)

**Dependência externa:** não se aplica. O ponto do card é justamente que
**silenciar é operação local e imediata** — nada nele pode esperar por rede.

## Escopo

- **In:** reprodução no aparelho com marcos registrados; `pause()` antes de
  `remove()`; teste de unidade da fila que prova a ordem das chamadas; medição
  do "tempo até o silêncio" antes e depois; `learnings/` se a causa for a
  prevista.
- **Out:** cancelar o turn no servidor (CARD-043). Barge-in de verdade — falar
  por cima sem tocar em botão é **V2** (ADR-0003), e o briefing avisa
  explicitamente para resistir à tentação de transformar este card naquilo.

## Critérios de aceite

- **Dado** o professor falando no aparelho, **quando** o aluno toca em gravar,
  **então** o som para em **menos de 200 ms** — medido no iPhone, com o número
  colado no card. (200 ms é o limiar de "instantâneo" percebido, e é da mesma
  ordem do gap p50 de 209 ms já medido.)
- **Dado** uma fila com três trechos, um tocando e dois pré-carregados,
  **quando** `limpar()` é chamado, **então** `pause()` é chamado **antes** de
  `remove()` em cada player — teste de unidade com player falso que registra a
  ordem.
- **Dado** o app em modo avião, **quando** o aluno toca em gravar durante o
  playback, **então** o som para igual. Silenciar não depende de rede.
- **Dado** um turn interrompido, **quando** o aluno grava e envia de novo,
  **então** nenhum trecho do turn anterior toca em momento algum — nem depois do
  turn novo começar.
- **Dado** a causa confirmada, **quando** o card fecha, **então** existe
  `docs/learnings/` com a regra que ela gera. Se a hipótese for **derrubada**, o
  card registra isso com a mesma clareza.

## Riscos

- **A hipótese pode estar errada.** É o risco principal, e por isso o card
  começa por reproduzir. Se `pause()` não resolver, a segunda linha é a sessão
  de áudio do iOS; se nenhuma das duas, o card vira spike e reporta.
- **O certificado expira em 2026-09-16** (CARD-037). Depois disso o app não
  abre e é preciso recompilar com o cabo. Este card **precisa do aparelho** —
  não dá para fechá-lo no Simulador, que é onde o bug não aparece.
- **Corrigir no lugar errado:** silenciar dentro de `useGravacao` acoplaria
  gravação a playback. O silêncio pertence à fila.

## Objetivo de aprendizado

Entender o ciclo de vida de um **objeto nativo compartilhado** (`SharedObject`
do `expo-modules-core`) e por que `remove()` não é `Dispose()`: em .NET o
`Dispose` é síncrono e determinístico no thread que chama; aqui a liberação
atravessa a ponte JS↔nativo e o recurso de áudio do sistema tem vida própria do
outro lado. É a diferença entre "soltei a referência" e "o som parou" — e é
exatamente a distinção que este bug materializa.

---

## Execução — sessão de 2026-09-10/11

**Sem o iPhone nesta sessão** (o desenvolvedor não estava com o aparelho). A
consequência foi declarada na abertura e não foi contornada: o critério dos
**200 ms medidos no aparelho fica em dívida**. O que esta sessão fez foi trocar
a reprodução no ouvido por duas evidências que não precisam dele — o **código
nativo do `expo-audio` instalado** e uma **medição no Simulador** que lê o
player pelo lado de dentro.

### 1. A hipótese do card estava certa na conclusão e errada no mecanismo

O card supunha: *"`remove()` libera o objeto compartilhado, mas o áudio já
entregue ao `AVPlayer` continua saindo **até o buffer esvaziar**"*. A leitura do
Swift instalado (`expo-audio@57.0.4`) mostra que não há buffer esvaziando coisa
alguma — **`remove()` simplesmente não cala nada.**

O caminho completo, com os arquivos:

| Passo | Arquivo | O que faz |
|---|---|---|
| `player.remove()` em JS | — | não há wrapper no iOS; cai direto no nativo |
| `Function("remove")` | `ios/AudioModule.swift:251` | chama `self.registry.remove(player)` — **e mais nada** |
| `AudioComponentRegistry.remove` | `ios/AudioComponentRegistry.swift:36` | `registryQueue.async(flags: .barrier) { players.removeValue(...) }` — larga a referência do **registro**, de forma **assíncrona** |

O que **não** acontece: `sharedObjectWillRelease()`
(`ios/AudioPlayer.swift:506`) → `teardownPlayer()` (`:321`) → **`ref.pause()`**
(`:335`). Esse é o único lugar do módulo que cala o `AVPlayer` num teardown, e
ele só roda quando o `SharedObject` é **liberado de verdade** — pelo
`release()` do JSI (`expo-modules-core/common/cpp/SharedObject.cpp:31-39` →
`SharedObjectRegistry.delete` → `sharedObjectWillRelease`), ou quando o coletor
de lixo do JavaScript recolhe o objeto.

Ou seja: depois do `remove()`, o objeto JS ainda está vivo (a nossa própria
`Map` o segurava), o objeto nativo ainda está vivo, o `AVPlayer` ainda está
tocando. Quando a `Map` é limpa, quem decide a hora do silêncio passa a ser o
**coletor de lixo** — que não tem prazo.

> **A distinção que o objetivo de aprendizado do card previu, materializada:**
> `remove()` não é `Dispose()`. Em .NET o `Dispose` é síncrono e determinístico
> na thread que chama. Aqui `remove()` é `registryQueue.async` + "larguei uma
> referência" — e o recurso de áudio do sistema continua do outro lado da ponte,
> tocando, até que alguém o pause ou o colete.

### 2. A medição, e por que ela não precisa de ouvido

Rota nova: `app/diagnostico-silencio.tsx`. Ela não tenta ouvir o som — ela
observa o **player nativo pelo lado de dentro**:

> enquanto o `AVPlayer` estiver vivo e tocando, o time observer instalado nele
> continua emitindo `playbackStatusUpdate` com o `currentTime` **avançando**.
> Ele só é desinstalado no `teardownPlayer()`.

Logo, "o `currentTime` avançou N ms depois do `remove()`" responde à mesma
pergunta que "o som continuou por N ms" — **sem alto-falante e sem aparelho**.
É um **proxy declarado**, não o som: prova que o player seguiu rodando, não que
ele seguiu audível. O número no ouvido continua sendo dívida.

As duas variantes, a 500 ms de um insumo de 2,3 s:

| Variante | Em T0 |
|---|---|
| `a` | `remove()` só — o código de antes deste card |
| `b` | `pause()` e depois `remove()` — a correção |

**As seis execuções, colhidas do log do Metro** (Simulador iPhone 17, iOS 26.5,
insumo de 2,3 s, `updateInterval: 50`):

```
variante=a · t(T0)=0.000s · AVANÇO DEPOIS DO REMOVE = 2300ms · +2521ms · 51 amostras · 50 playing=true
variante=a · t(T0)=0.106s · AVANÇO DEPOIS DO REMOVE = 2194ms · +2195ms · 46 amostras · 45 playing=true
variante=a · t(T0)=0.292s · AVANÇO DEPOIS DO REMOVE = 2008ms · +2008ms · 86 amostras · 84 playing=true
variante=a · t(T0)=0.281s · AVANÇO DEPOIS DO REMOVE = 2019ms · +2008ms · 86 amostras · 84 playing=true
variante=b · t(T0)=0.295s · AVANÇO DEPOIS DO REMOVE =    2ms ·   +30ms ·  1 amostra  ·  0 playing=true
variante=b · t(T0)=0.279s · AVANÇO DEPOIS DO REMOVE =    1ms ·   +34ms ·  1 amostra  ·  0 playing=true
```

**A hipótese do card estava certa na conclusão e errada no mecanismo, e a
diferença importa.** O card dizia "até o buffer esvaziar" — o que sugere dezenas
ou poucas centenas de ms, um problema de margem. A medição mostra **o resto
inteiro do arquivo**: 2,0–2,3 s de um trecho de 2,3 s. Não havia buffer
drenando; **não havia nada calando o player**. O "tempo até o silêncio" do
código antigo não tinha teto — era o que faltasse do trecho.

Com `pause()` antes: **1–2 ms**, último sinal de vida em +30 ms, e **zero**
amostras com `playing: true`. O critério dos 200 ms é atendido com folga de duas
ordens de grandeza — **no Simulador, por proxy**. No aparelho, no ouvido, é
dívida.

### 3. O que foi corrigido

| Arquivo | Mudança |
|---|---|
| `src/features/turno/silencio.ts` **(novo)** | `silenciarELiberar()` — `pause()` e **então** `remove()`, cada um no próprio `try`. Módulo **sem imports**, para ser testável em Node puro (ADR-0061) |
| `src/features/turno/useFilaDePlayback.ts` | `soltarTudo` e `renovar` passam a usar a função; **geração** que sobe a cada `limpar()`; inscrições dos listeners guardadas e removidas |
| `src/features/turno/useTurno.ts` | `recuperarAudio` confere `turnAtualRef.current !== id` **depois** do `await` |
| `src/features/gravacao/TelaConversa.tsx` | a ordem "calar síncrono antes de gravar assíncrono" vira invariante comentada |

**O achado que o card não previa** (aprovado pelo desenvolvedor na abertura):
`recuperarAudio` fazia `GET /v1/turns/{id}` **sem `AbortSignal`** e, na volta,
chamava `fila.renovar()` — que cria player e toca. O `abort()` do `limpar()` não
alcança essa requisição, porque é outra. Com o turn morto, isso fazia o trecho
antigo voltar a falar **depois** do turn novo começar — exatamente o quarto
critério de aceite. Cura: a geração na fila (barra os listeners dos players
zumbis) e a conferência do `turnAtualRef` (barra a volta da rede).

### 4. Critérios de aceite, um a um

| Critério | Desfecho |
|---|---|
| som para em < 200 ms **no iPhone** | ❌ **dívida** — sem aparelho nesta sessão. Proxy no Simulador: **1–2 ms** vs. 2008–2300 ms antes |
| `pause()` antes de `remove()` em cada player, com dublê | ✅ `silencio.test.ts`, 5 testes. Gate provado: ordem invertida ⇒ **3 de 5 vermelhos** em 105 ms; revertido ⇒ 5 verdes |
| modo avião: o som para igual | ✅ por construção e por teste — `silenciarELiberar` é síncrona e não toca em rede, relógio ou plataforma (teste 5). **Não verificado com o rádio desligado num aparelho** |
| nenhum trecho do turn anterior toca | ✅ geração na fila + guarda do `turnAtualRef`. **Verificado por leitura e tipo, não por execução do cenário** |
| `learnings/` com a regra | ✅ [LEARNING-0006](../learnings/0006-remove-nao-e-dispose-e-o-gate-que-faltava-era-o-teste.md) |

### 5. Item de ADR da DoD — critério citado

O **bug** não gera ADR (`docs/adr/README.md`, §"Quando NÃO escrever ADR":
*"correções de bug sem mudança de design → isso vai para `docs/learnings/`"*).
Mas o **runner de teste** gera, e o card não previa isso: critério **1**
(introduz dependência externa — `vitest`, e com ele `esbuild`) e critério **6**
(contraria convenção estabelecida — o ADR-0043 item 6 decidiu por escrito que o
cliente não teria gate de teste). Resultado:
[**ADR-0061**](../adr/0061-o-primeiro-teste-do-cliente-vitest-sobre-logica-extraida.md).

### 6. Regra do explicador

**Uma pergunta, no ponto da decisão** — feita **antes** de escrever a correção,
depois de ler o Swift e **antes** de rodar o experimento:

> *"`player.remove()` sem `pause()` antes: o som para na hora, para no fim do
> buffer, ou não para? E o que a medição no aparelho vai mostrar como 'tempo até
> o silêncio' em cada caso?"*

- **1ª resposta: "não sei dizer".**
- Explicada com a demonstração acima (as seis execuções) e com o caminho no
  Swift instalado. A resposta é **"não para"** — a terceira opção, que nem o
  card nem eu havíamos previsto como a mais provável.
- **Reformulada uma vez, na mesma sessão:** *"largando a última referência JS em
  `players.current.clear()`, o som parava sozinho em algum momento?"*
- **2ª resposta: "as duas, o que vier primeiro" — correta.** Fim do arquivo ou
  coleta de lixo, e qual chega antes depende da duração do trecho e da pressão
  de memória. É a explicação de por que o bug se comportava de forma
  inconsistente.

**Desfecho: respondida.** Item verde.

### 7. Dívidas explícitas

| O que ficou | Por quê | Gatilho |
|---|---|---|
| **Os 200 ms medidos no iPhone**, antes e depois | não havia aparelho na sessão | próxima sessão com o iPhone — a rota `/diagnostico-silencio` já está pronta e o roteiro é o deep link. **Certificado expira em 2026-09-16** |
| **Modo avião verificado de fato** | idem | mesma sessão |
| **O cenário "turn interrompido, grava de novo" executado ponta a ponta** | exige backend de pé + aparelho | mesma sessão |
| Ordenar `setAudioModeAsync` depois do silêncio (hipótese 2 do card) | **não foi preciso**: a hipótese 1 explicou 100% do avanço medido. A hipótese 2 não foi testada nem descartada | se o som ainda escapar no aparelho depois desta correção |
