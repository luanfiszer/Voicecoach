# CARD-042 — Regravar cala o professor: o bug do playback que sobrevive ao `limpar()`

- **ID:** CARD-042
- **Épico:** Qualidade da conversa (briefing 2026-09-09, ponto 2 — lado do cliente)
- **Esforço:** P
- **Status:** backlog
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
