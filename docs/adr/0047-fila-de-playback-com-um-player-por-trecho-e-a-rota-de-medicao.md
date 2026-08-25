# ADR-0047 — Fila de playback com um player por trecho, e a rota de medição como instrumento

- **Status:** aceito
- **Data:** 2026-08-25
- **Relacionado:** [ADR-0023](0023-ciclo-de-vida-do-turn-com-entrega-em-cascata.md)
  (ordem por `index`), [ADR-0041](0041-id-estruturado-do-evento-sse-e-retomada-derivada-do-banco.md)
  (dedup), [ADR-0044](0044-dependencias-de-arranque-do-app-expo-e-convivencia-com-pnpm.md)
  (dependências do app), [ADR-0021](0021-prompt-caching-adiado-o-limiar-medido-nao-e-alcancado.md)
  (o precedente de registrar o número que **não** deu certo)
- **Critérios de obrigatoriedade** (`docs/adr/README.md`): **1 — introduz uma
  dependência externa** (`expo-asset`) e **5 — seria difícil de reverter**: a
  fila é a forma como o produto entrega o seu diferencial, e trocá-la depois de
  a UI depender dela custa mais que uma sessão.

## Contexto

A cascata (ADR-0023) entrega de 3 a 6 trechos de áudio por turn, e o critério de
aceite do CARD-012 pede **gap audível < 150 ms** entre eles. Um buraco
perceptível entre frases desfaz o ganho: o aluno ouve um professor gaguejando.

Duas coisas precisavam de decisão e nenhum ADR as cobria: **como encadear os
trechos** e **como medir se o encadeamento funcionou** — numa máquina em que o
agente não consegue tocar na tela do Simulador (o `osascript` está sem acesso
assistivo, conferido no CARD-011), e onde `p50` exige repetição.

## Decisão

**Há um `AudioPlayer` por trecho, criado no instante em que o evento `chunk`
chega. A ordem de playback é o `index`, comparado numericamente. E a medição é
uma rota do app, disparada por deep link, com insumo fixo.**

### 1. Um player por trecho — criar o player **é** o prefetch

`createAudioPlayer({ uri })` começa a carregar o áudio na criação. Criá-lo quando
o evento chega faz o download e a decodificação do trecho N+1 acontecerem
**enquanto o N ainda toca**. Com um player só e `replace(url)` a cada trecho, o
carregamento do N+1 só começaria quando o N terminasse, caindo **dentro** do gap.

**Consequência de dependências:** nada de `expo-file-system`. O buffer é do
próprio player, e a régua do ADR-0044 continua alta.

### 2. Ordem por `index`, comparação numérica

ADR-0023 item 2: *"o instante de criação é medição, a ordem é contrato de
playback"*. A comparação é `a.index - b.index` e não de string, porque
`'chunk:10' < 'chunk:2'` — o mesmo bug que o ADR-0041 evitou no servidor.

### 3. Dedup por índice, na entrada da fila

Antes de criar o player. Criar dois players para o mesmo trecho tocaria a frase
duas vezes, que é o modo de falha do ADR-0041 item 3 chegando ao alto-falante.

### 4. Os players são objetos nativos e são liberados à mão

Eles não são estado do React: vivem em `useRef` e exigem `remove()`, ou a
memória do áudio vaza. É a diferença que não existe no React web, onde nada
sobrevive ao garbage collector do JavaScript.

### 5. A rota `/medicao` é instrumento, e declara o que **não** mede

Disparada por
`exp://…/--/medicao?execucoes=10&auto=1`, ela roda N turns sozinha e mostra p50.
O insumo é um WAV fixo empacotado (o mesmo das medições §§2–10 de
`medicao-latencia.md`) — **`expo-asset`** entra por isso, e é a única dependência
nova deste card. *Gatilho para removê-la:* a medição passar a usar o microfone.

Insumo constante torna as N execuções comparáveis e isola o que o card mede.
**O que ela não mede fica escrito no próprio arquivo:** não há gravação, então o
marco 1 é *"o envio começou"*, e não *"o dedo saiu do botão"*.

### 6. A resolução do instrumento é parte do número

O `playbackStatusUpdate` do `expo-audio` tem `updateInterval` **default de
500 ms**. A primeira leva de 10 execuções mediu gap p50 de **594 ms** —
praticamente uma tick, e quase idêntico em 6 de 7 rodadas. **Isso é o
instrumento, não o produto**: um relógio de 500 ms não pode julgar um critério de
150 ms. O `updateInterval` da fila é fixado em **50 ms** por causa disso, e o
número reportado no card traz a resolução junto.

É a mesma disciplina do ADR-0021 e da `medicao-latencia.md` §1: número sem método
declarado é anedota, e um número cuja incerteza é maior que o critério não
decide nada.

## Alternativas consideradas

### Alternativa A — Um player só, com `replace(url)` a cada trecho

- **O que é:** o caminho mais econômico em memória: um objeto nativo, reusado.
- **Por que foi rejeitada:** põe download e decodificação **dentro** do gap, que
  é exatamente o que o critério de aceite proíbe. Fica registrada como a saída
  se a memória de N players se mostrar um problema real em turns longos.

### Alternativa B — Baixar os trechos para o sistema de arquivos antes de tocar

- **O que é:** `expo-file-system` baixa cada trecho, e o player toca do arquivo
  local.
- **A favor:** controle explícito sobre quando os bytes existem, e o download
  sai comprovadamente do caminho crítico.
- **Por que foi rejeitada:** uma dependência e um estágio a mais (rede → disco →
  decodificador) para resolver um problema que o próprio player já resolve ao ser
  criado cedo. **Gatilho para reabrir:** o gap medido continuar dominado por
  download depois de a resolução do instrumento estar fina.

### Alternativa C — Playlist nativa (`AudioPlaylist` do `expo-audio`)

- **O que é:** entregar a lista ao módulo e deixar o encadeamento com ele.
- **Por que foi rejeitada:** a lista **não existe inteira** quando o playback
  começa — é essa a cascata. Uma playlist que aceite itens acrescentados ao vivo
  esconderia a única métrica que o card veio produzir (o gap por trecho), e o
  instante audível deixaria de ser observável do lado do JavaScript.

### Alternativa D — Medir tocando na tela, sem rota de medição

- **O que é:** o desenvolvedor grava e toca dez vezes.
- **Por que foi rejeitada:** dez execuções com dez falas diferentes medem
  **também** a variação do insumo, e o agente não consegue disparar nenhuma
  delas. A rota não substitui a verificação com microfone real — ela dá a
  repetição que o `p50` exige.

## Consequências

**Positivas**

- O prefetch sai de graça, sem estágio de arquivo e sem dependência de IO.
- A medição vira **executável a partir do terminal**, o que a torna repetível
  entre sessões e comparável quando algo mudar no pipeline.
- A fila é um hook sem UI: o gap pode ser medido sem a tela de conversa no meio.

**Negativas — o preço aceito**

- **N players nativos vivos por turn.** Para 3 a 6 trechos curtos é irrelevante;
  para um turn com dezenas seria memória de áudio decodificado acumulada, e a
  Alternativa A volta à mesa.
- **`expo-asset` entra**, e com ela um WAV **duplicado** no repositório (o mesmo
  arquivo já existe em `backend/tests/fixtures/stt/`). O Metro empacota a partir
  de `apps/mobile/`, então apontar para fora do app atravessaria a fronteira do
  monorepo. Duplicação deliberada, com a exceção anotada no `.gitignore`.
- **O `updateInterval` de 50 ms é tráfego a mais na ponte nativa**, dez vezes o
  default, durante todo o playback. Aceito porque a alternativa é não conseguir
  medir o critério — mas é custo real de bateria num aparelho.
- **A rota de medição é código de produto que nenhum aluno usará.** Ela fica, e
  não vira spike descartável, porque o número precisa ser refeito toda vez que o
  pipeline mudar. É a diferença entre um spike e um instrumento.

**Equivalente mental .NET:** é a diferença entre um `BufferBlock` que só puxa o
próximo item quando o anterior termina e um com `BoundedCapacity` maior que 1,
que mantém o próximo já materializado — com a diferença de que aqui "materializar"
significa rede e decodificação de áudio, não alocação.
