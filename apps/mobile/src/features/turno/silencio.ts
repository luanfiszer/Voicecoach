/**
 * Calar e soltar um player de áudio — a ordem, e o porquê dela (CARD-042).
 *
 * Módulo **sem import nenhum**, e isso é a decisão, não o acaso: é o que permite
 * testá-lo em Node puro, sem `jest-expo`, sem preset de React Native e sem mock
 * de módulo nativo (ADR-0061). Encostar em `expo-audio` aqui traria o runtime
 * inteiro do RN para dentro do teste de um laço de três linhas.
 */

/**
 * O mínimo que a fila precisa de um player para calá-lo e soltá-lo.
 *
 * **Por que um tipo estrutural e não `AudioPlayer`:** em TypeScript a
 * compatibilidade é por FORMA, não por declaração — nada precisa dizer que
 * implementa isto. É o que dispensa framework de mock: o dublê do teste é um
 * objeto literal com `playing`, `pause` e `remove`, e se esta porta ganhar um
 * método novo, quem reprova o dublê é o `tsc`, com o teste ainda verde. (É a
 * Q7 da fila de perguntas, do lado do cliente.)
 */
export type PlayerSilenciavel = {
  /** Se `false`, o player já não está tocando — `pause()` nele é dispensável. */
  playing: boolean;
  pause: () => void;
  remove: () => void;
};

/**
 * Cala cada player que ainda toca e **só então** libera todos. A ordem é o
 * contrato (CARD-042); o `if (player.playing)` é o achado de um card seguinte
 * (o bug do "não ouve nada" na segunda gravação, sessão de teste em aparelho
 * físico — o Simulador não tem microfone e nunca o revelou).
 *
 * `remove()` do `expo-audio` **não é `Dispose()`**: no iOS ele cai em
 * `AudioComponentRegistry.remove`, que só larga a referência do registro — e
 * larga num `registryQueue.async`. Ele **não** chama `teardownPlayer()`, que é
 * quem tem o `ref.pause()`. Enquanto o objeto JS estiver vivo, o `AVPlayer`
 * segue tocando; quando o objeto JS morre, quem decide a hora é o **coletor de
 * lixo**. "Soltei a referência" nunca foi "o som parou".
 *
 * **`pause()` não é de graça mesmo quando o player já parou sozinho.** O
 * módulo nativo do `expo-audio` agenda, a CADA `pause()`, uma desativação da
 * `AVAudioSession` inteira **100 ms depois** (`deactivateSession()`, em
 * `AudioModule.swift`) — inclusive num player que já tinha terminado de tocar
 * minutos antes. A fila nunca esvazia `players` sozinha quando um trecho
 * termina (só em `limpar()`), então todo turn novo cala de novo os players do
 * turn ANTERIOR, já parados. Isso agenda uma desativação de sessão que
 * detona ~100 ms depois — bem no meio da gravação que `useGravacao.iniciar()`
 * acabou de começar, cortando o microfone quase no instante em que ele liga.
 * Medido em aparelho físico (o Simulador não tem microfone para revelar isto):
 * três gravações truncadas em ~90–140 ms, sempre a partir da SEGUNDA
 * gravação de uma sessão — nunca a primeira, porque só a partir dela existe
 * player parado sobrando na fila para calar de novo. Pular o `pause()` de
 * quem já não toca elimina o gatilho sem abrir mão de calar quem interrompe
 * uma resposta em andamento.
 *
 * Cada chamada tem o próprio `try`: um `pause()` que lança não pode fazer o
 * `remove()` ser pulado, ou o vazamento de memória entra pela porta que a
 * correção do som abriu.
 */
export function silenciarELiberar(players: Iterable<PlayerSilenciavel>): void {
  for (const player of players) {
    if (player.playing) {
      try {
        player.pause();
      } catch {
        // Um player que nunca carregou pode recusar o `pause`; seguimos.
      }
    }
    try {
      player.remove();
    } catch {
      // Um player já removido lança; não é falha do produto.
    }
  }
}
