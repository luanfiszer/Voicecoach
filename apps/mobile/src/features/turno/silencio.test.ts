/**
 * O primeiro teste do cliente (ADR-0061).
 *
 * Ele existe por um motivo específico: a ordem `pause()` → `remove()` é uma
 * **invariante invisível**. Trocá-la não quebra compilação, não quebra lint, não
 * quebra tela nenhuma — e o sintoma aparece só no aparelho, no ouvido de quem
 * usa. É exatamente a classe de regra que só um teste segura.
 *
 * O dublê é um objeto literal: sem framework de mock, sem `jest.fn()`. Em
 * TypeScript a compatibilidade é **estrutural** — ter `pause` e `remove` já
 * satisfaz `PlayerSilenciavel`. Se a porta ganhar um método, o `tsc` reprova
 * este arquivo com o teste ainda verde (Q7, do lado do cliente).
 */

import { describe, expect, it } from 'vitest';

import { type PlayerSilenciavel, silenciarELiberar } from './silencio';

/** Um player falso que só sabe dizer em que ordem foi chamado. */
function playerFalso(nome: string, registro: string[]): PlayerSilenciavel {
  return {
    pause: () => registro.push(`${nome}.pause`),
    remove: () => registro.push(`${nome}.remove`),
  };
}

describe('silenciarELiberar', () => {
  it('cala antes de soltar, em cada player', () => {
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

  it('solta o player mesmo quando o pause lança', () => {
    // Um player que nunca carregou pode recusar o `pause`. Se isso pulasse o
    // `remove`, a correção do som teria aberto um vazamento de memória.
    const registro: string[] = [];
    const recalcitrante: PlayerSilenciavel = {
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
