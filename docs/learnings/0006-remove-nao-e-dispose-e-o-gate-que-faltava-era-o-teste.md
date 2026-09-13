# LEARNING-0006 — `remove()` não é `Dispose()`: soltar a referência não parou o som

- **Data:** 2026-09-11
- **Card/sessão relacionado:** CARD-042 (origem do sintoma: primeiro uso real,
  briefing de 2026-09-09, ponto 2)

## Sintoma

*"Ao errar a gravação e tentar recomeçar, o app continua falando."*

O aluno toca em gravar durante a resposta do professor. O código faz tudo o que
deveria — `TelaConversa` chama `turno.limpar()`, que chama `fila.limpar()`, que
percorre os players e chama `remove()` em cada um. E o professor continua
falando por cima da gravação nova.

Nenhum gate acusou: compilava, passava no Biome, passava no `tsc --strict`, e
nenhuma tela mudava de comportamento. O sintoma existia só no ouvido de quem
usava o app.

## Causa raiz

**`player.remove()` do `expo-audio` não pausa o áudio. Ele não pausa nada.**

No iOS, o caminho é:

```
player.remove()  (JS, sem wrapper)
  → AudioModule.swift:251        Function("remove") { registry.remove(player) }
  → AudioComponentRegistry:36    registryQueue.async(flags: .barrier) {
                                   players.removeValue(forKey: player.id)
                                 }
```

Larga a referência do **registro**, de forma **assíncrona**, e acabou. O único
lugar do módulo que cala o `AVPlayer` num teardown é
`teardownPlayer()` (`AudioPlayer.swift:335`, `ref.pause()`), chamado apenas por
`sharedObjectWillRelease()` — que roda no `release()` do JSI
(`expo-modules-core/common/cpp/SharedObject.cpp:31-39`) ou quando o **coletor de
lixo do JavaScript** recolhe o objeto pareado.

Como a `Map` da fila ainda segurava o player, nada disso acontecia. E depois de
`players.current.clear()`, quem passava a decidir a hora do silêncio era o **GC**
— ou o fim do próprio arquivo, o que viesse primeiro. Nenhum dos dois é
controlável, e é por isso que o bug se comportava de forma inconsistente.

**Medido** (Simulador iPhone 17, insumo de 2,3 s, `updateInterval: 50`, o
`currentTime` observado depois do `remove()` como proxy de "o player seguiu
rodando"):

| Variante | Avanço depois do `remove()` |
|---|---|
| `remove()` só | **2300 / 2194 / 2008 / 2019 ms** — o resto inteiro do arquivo |
| `pause()` + `remove()` | **2 / 1 ms**, zero amostras com `playing: true` |

O erro de raciocínio por trás do código antigo tem nome, e ele vem do meu
background: **eu tratei `remove()` como `Dispose()`**. Em .NET, `Dispose()` é
síncrono, determinístico, roda na thread que chama e libera o recurso ali. Aqui
`remove()` é `registryQueue.async` mais "soltei uma referência", e o recurso de
áudio do sistema vive do outro lado da ponte JS↔nativo, com ciclo de vida
próprio. **"Soltei a referência" e "o som parou" são dois eventos diferentes,
em tempos diferentes, e um não implica o outro.**

Agravante: a hipótese escrita no card dizia *"continua saindo até o buffer
esvaziar"* — o que teria sido um problema de margem, de dezenas de ms. A medição
mostrou que não havia buffer drenando coisa nenhuma. **A hipótese estava certa na
conclusão e errada no mecanismo, e só a execução separou as duas.**

## Como descobri

Não pelo Simulador e não pelo aparelho — por **ler o código nativo da dependência
instalada**, e depois medir.

O aparelho não estava disponível na sessão. Em vez de adiar o card inteiro, a
investigação foi para `node_modules/.pnpm/expo-audio@57.0.4/.../ios/*.swift`, e
lá o caminho de `remove()` estava escrito. A partir da leitura veio o
instrumento: se o `AVPlayer` continua vivo, o time observer dele continua
emitindo `playbackStatusUpdate` com o `currentTime` avançando — logo, "o som
continuou por N ms" podia ser medido **sem ouvido e sem aparelho**, no
Simulador.

## Como evitar

**Ler o código da dependência é barato e quase nunca é a primeira coisa que eu
faço.** O `node_modules` está no disco; o Swift do `expo-audio` são 3.200 linhas
e a resposta estava em três arquivos. A leitura custou minutos e produziu uma
certeza que nenhuma quantidade de tentativa e erro no aparelho teria produzido —
porque no aparelho eu veria *que* o som continua, não *por quê*.

E: **invariante que só o ouvido verifica precisa de teste**, ou ela volta a ser
violada. A ordem `pause()` → `remove()` não quebra build, tipo, lint nem tela.
Foi o que fez o CARD-042 existir, e é o que o ADR-0061 passou a cobrir.

## Regra criada no CLAUDE.md

> **Objeto nativo não se "solta", se desliga primeiro.** Antes de liberar um
> recurso do outro lado da ponte JS↔nativo (player de áudio, gravador, câmera,
> socket), **pare-o explicitamente** e só então solte a referência. `remove()`,
> `release()` e afins **não são `Dispose()`**: a liberação pode ser assíncrona,
> pode depender do coletor de lixo, e o recurso do sistema continua vivo até
> alguém mandá-lo parar. Quando o comportamento de uma dependência nativa
> importar, **leia o código dela em `node_modules` antes de supor** — e, se a
> invariante que sair daí for invisível para lint, tipo e tela, ela precisa de
> um teste (ADR-0061).
