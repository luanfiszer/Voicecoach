/**
 * O primeiro teste do cliente (ADR-0061).
 *
 * Ele existe por um motivo específico: a ordem `pause()` → `remove()` é uma
 * **invariante invisível**. Trocá-la não quebra compilação, não quebra lint, não
 * quebra tela nenhuma — e o sintoma aparece só no aparelho, no ouvido de quem
 * usa. É exatamente a classe de regra que só um teste segura.
 *
 * O dublê é um objeto literal: sem framework de mock, sem `jest.fn()`. Em
 * TypeScript a compatibilidade é **estrutural** — ter `playing`, `pause` e
 * `remove` já satisfaz `PlayerSilenciavel`. Se a porta ganhar um método, o
 * `tsc` reprova este arquivo com o teste ainda verde (Q7, do lado do cliente).
 */

import { describe, expect, it } from 'vitest';

import { type PlayerSilenciavel, silenciarELiberar } from './silencio';

/** Um player falso que só sabe dizer em que ordem foi chamado. */
function playerFalso(
  nome: string,
  registro: string[],
  playing = true,
): PlayerSilenciavel {
  return {
    playing,
    pause: () => registro.push(`${nome}.pause`),
    remove: () => registro.push(`${nome}.remove`),
  };
}

describe('silenciarELiberar', () => {
  it('cala antes de soltar, em cada player que ainda toca', () => {
    const registro: string[] = [];
    silenciarELiberar([playerFalso('p0', registro)]);

    expect(registro).toEqual(['p0.pause', 'p0.remove']);
  });

  it('percorre a fila inteira — o que toca e os pré-carregados', () => {
    // O cenário do critério de aceite: três trechos, um tocando e dois
    // prontos. Nenhum deles pode sobreviver ao `limpar()`.
    const registro: string[] = [];
    silenciarELiberar([
      playerFalso('tocando', registro),
      playerFalso('pronto1', registro),
      playerFalso('pronto2', registro),
    ]);

    expect(registro).toEqual([
      'tocando.pause',
      'tocando.remove',
      'pronto1.pause',
      'pronto1.remove',
      'pronto2.pause',
      'pronto2.remove',
    ]);
  });

  it('não chama pause() num player que já não toca — só remove', () => {
    // O achado da sessão de teste em aparelho físico: `pause()` no
    // `expo-audio` agenda uma desativação da `AVAudioSession` inteira 100ms
    // depois, MESMO num player que já tinha terminado sozinho. Como a fila só
    // esvazia `players` em `limpar()`, todo turn novo calava de novo os
    // players do turn ANTERIOR — e a desativação tardia cortava o microfone
    // da gravação que tinha acabado de começar. Pular o `pause()` de quem já
    // não toca elimina o gatilho.
    const registro: string[] = [];
    silenciarELiberar([playerFalso('jaTerminou', registro, false)]);

    expect(registro).toEqual(['jaTerminou.remove']);
  });

  it('mistura: cala quem toca, só solta quem já parou', () => {
    const registro: string[] = [];
    silenciarELiberar([
      playerFalso('tocando', registro, true),
      playerFalso('parado', registro, false),
    ]);

    expect(registro).toEqual(['tocando.pause', 'tocando.remove', 'parado.remove']);
  });

  it('solta o player mesmo quando o pause lança', () => {
    // Um player que nunca carregou pode recusar o `pause`. Se isso pulasse o
    // `remove`, a correção do som teria aberto um vazamento de memória.
    const registro: string[] = [];
    const recalcitrante: PlayerSilenciavel = {
      playing: true,
      pause: () => {
        throw new Error('player não carregado');
      },
      remove: () => registro.push('recalcitrante.remove'),
    };

    expect(() => silenciarELiberar([recalcitrante])).not.toThrow();
    expect(registro).toEqual(['recalcitrante.remove']);
  });

  it('não deixa um player que lança impedir o silêncio dos outros', () => {
    // O modo de falha que isto impede é o pior de todos: um player já removido
    // lança no `remove`, e o resto da fila continua falando.
    const registro: string[] = [];
    const explosivo: PlayerSilenciavel = {
      playing: true,
      pause: () => registro.push('explosivo.pause'),
      remove: () => {
        throw new Error('já removido');
      },
    };

    silenciarELiberar([explosivo, playerFalso('seguinte', registro)]);

    expect(registro).toEqual(['explosivo.pause', 'seguinte.pause', 'seguinte.remove']);
  });

  it('não depende de rede, relógio ou plataforma', () => {
    // A prova do critério "em modo avião o som para igual": a função é
    // síncrona e não toca em nada além dos dois métodos do player. Se algum dia
    // alguém puser um `await` aqui, este teste para de fazer sentido — e é
    // esse o aviso.
    const registro: string[] = [];
    const retorno = silenciarELiberar([playerFalso('p0', registro)]);

    expect(retorno).toBeUndefined();
    expect(registro).toHaveLength(2);
  });
});
