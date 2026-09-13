# LEARNING-0008 — `pause()` também não é inofensivo: ele agenda desligar a sessão inteira 100ms depois

- **Data:** 2026-09-13
- **Card/sessão relacionado:** teste em aparelho físico (iPhone), fora do
  fluxo de um card — achado ao usar o app de verdade pela primeira vez com
  microfone real. Mesma área do [LEARNING-0006] (`expo-audio`, ciclo de vida
  de player), consequência que o CARD-042 não tinha como prever.

## Sintoma

*"Quando eu vou dar a resposta ele não ouve nada do que eu disse, preciso
regravar."*

A primeira gravação de uma sessão do app sempre funcionava: transcrição
correta, correção certa, resposta do professor tocando. A partir da
**segunda** gravação, o áudio enviado chegava correto no formato mas **vazio**
— um `.m4a` bem formado, cabeçalho normal, e só ~36 bytes de payload real
depois dele (medido com `afinfo`: "estimated duration: 0.091429 sec", contra
os 15–20 s reais que o aluno tinha falado). Sempre a partir da segunda
gravação; nunca a primeira.

Nenhum gate acusou — de novo. O Simulador nunca teria revelado isto: ele não
tem microfone (medido em sessão anterior, RMS = 0 em toda tentativa), e é por
isso que este bug só apareceu ao testar em aparelho físico pela primeira vez,
mesmo com o resto do app já validado em dezenas de execuções no Simulador.

## Causa raiz

**`silenciarELiberar()` (CARD-042) pausa TODO player que ainda está na fila
antes de soltá-lo — inclusive um que já tinha terminado de tocar sozinho
minutos antes.** A fila (`useFilaDePlayback`) nunca esvazia `players` quando
um trecho termina; só esvazia em `limpar()`. Então todo turn novo cala de novo
os players do turn ANTERIOR, mesmo que eles já estivessem mudos havia tempo.

Isso seria inofensivo — **se `pause()` fosse só "pausar"**. Ele não é. No iOS:

```
AudioModule.swift, Function("pause"):
  player.ref.pause()
  if !player.keepAudioSessionActive {
    deactivateSession()
  }

deactivateSession():
  Task {
    try? await Task.sleep(for: .milliseconds(100))
    let hasActivePlayables = registry.allPlayables.contains { $0.isPlaying }
    guard !hasActivePlayables else { return }
    try? AVAudioSession.sharedInstance().setActive(false, options: [.notifyOthersOnDeactivation])
  }
```

Toda chamada a `pause()` — mesmo num player já parado — agenda uma
**desativação da `AVAudioSession` inteira, 100ms depois**, condicionada só a
"nenhum player está tocando **naquele momento futuro**". A sequência real:

1. Segunda gravação começa: `TelaConversa` chama `turno.limpar()` →
   `fila.limpar()` → `silenciarELiberar()` pausa os players (já mudos) do
   turn 1. Isso agenda a `Task` de 100ms.
2. Na mesma função síncrona, `gravacao.iniciar()` roda: ativa a sessão
   (`.playAndRecord`) e chama `recorder.record()`. A gravação começa de
   verdade — o `.m4a` tem cabeçalho normal porque começou normal.
3. ~100ms depois, a `Task` agendada no passo 1 dispara. Nenhum player está
   tocando (eles já tinham terminado antes), então o guard passa, e
   `setActive(false)` **desliga a sessão de áudio inteira — com a gravação
   nova em andamento dentro dela.** O microfone para de capturar quase no
   instante em que começou: daí os ~90ms de áudio real, sempre parecidos,
   sempre a partir da segunda gravação (a primeira não tem player nenhum na
   fila para pausar, então nunca agenda a `Task`).

O padrão de raciocínio errado, de novo: **assumi que "pausar um player que já
não toca" é uma operação sem efeito colateral.** Não é — o efeito colateral
não está no player, está no **estado compartilhado da sessão de áudio**, e ele
atravessa para o próximo consumidor dela (o gravador) sem nenhum aviso.

## Como descobri

**Não adivinhando — medindo o arquivo real que chegou ao servidor.** Com o
backend rodando localmente durante o teste, consultei o Postgres
(`SELECT audio_duration, transcript FROM turns ORDER BY created_at DESC`) e vi
três turns com `audio_duration = 00:00:00.139312` **idêntico**, transcript
vazio, no meio de turns normais de 15–20s. Um valor idêntico repetido é sinal
de mecanismo, não de sorte.

Baixei o `.m4a` real do MinIO (`boto3.client('s3').download_file(...)`) e
rodei `afinfo` (utilitário nativo do macOS) nele: arquivo válido, 57344 bytes
de cabeçalho, **36 bytes de áudio real**. Isso eliminou de vez a hipótese de
"leitura truncada no upload" (um blob cortado não produziria um container MP4
bem formado) e apontou para "o gravador nativo genuinamente só capturou ~90ms".

Daí, mesma técnica do LEARNING-0006: **ler o Swift da dependência instalada**
(`node_modules/expo-audio/ios/AudioModule.swift`) em vez de tentar reproduzir
por tentativa e erro. A busca por `deactivateSession`/`setActive` achou o
`Task` de 100ms na função `pause()` — e a partir daí o mecanismo bateu exatamente
com o timing observado.

## Como evitar

**Um `pause()` num player que não está tocando não é grátis nesta biblioteca —
não chame um sem checar.** A correção foi em `silencio.ts`: `PlayerSilenciavel`
ganhou o campo `playing`, e `silenciarELiberar()` só chama `pause()` quando
`player.playing` é verdadeiro (sempre chama `remove()`, como antes). Testado
em `silencio.test.ts` sem mock nativo, no padrão do ADR-0061 — o dublê agora
declara `playing` e o teste cobre os dois casos (toca / já parado).

**A régua de "todo `pause()`/`remove()` de objeto nativo é suspeito até provar
o contrário" (LEARNING-0006) ganha um corolário: o efeito colateral pode não
ser no OBJETO que você está chamando, pode ser em outro subsistema
compartilhado** (aqui, a sessão de áudio inteira, usada tanto por playback
quanto por gravação). Ler o código nativo não basta perguntar "o que este
método faz no objeto"; é preciso perguntar "o que mais este método toca que
não é o objeto".

**O Simulador não ia revelar isto nunca.** Sem microfone real, não há nada
para o `setActive(false)` interromper — a "gravação" no Simulador já não
capta nada, então cortá-la 100ms depois não muda um resultado que já era
silêncio. Reforça o item do ADR-0054/skill do cliente: dívida do que só o
aparelho físico prova precisa ficar **escrita**, não assumida como "testado".

## Regra a considerar para o CLAUDE.md

O CLAUDE.md já tem a regra do LEARNING-0006 ("objeto nativo não se solta, se
desliga primeiro"). Este achado é específico o bastante (efeito colateral
cruzando de playback para gravação via estado de sessão compartilhado) para
ficar registrado aqui, sem duplicar a regra geral — mas se o padrão se repetir
uma terceira vez em outro par de subsistemas nativos, é sinal de generalizar
a regra do CLAUDE.md para citar "estado compartilhado entre objetos nativos
irmãos", não só o objeto chamado.
