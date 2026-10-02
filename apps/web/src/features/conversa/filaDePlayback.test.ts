/**
 * A fila de playback da web (CARD-065), com elementos de áudio de mentira:
 * ordem por índice, dedup, prefetch, medição de gap, vigia de carga e — o
 * análogo web do LEARNING-0006 — `pause()` antes de soltar.
 */

import { describe, expect, it } from 'vitest';

import { type AudioDaFila, criarFila, type EstadoDaFila } from './filaDePlayback';

class AudioFalso implements AudioDaFila {
  src = '';
  preload = '';
  chamadas: string[] = [];
  private ouvintes = new Map<string, (() => void)[]>();

  async play(): Promise<void> {
    this.chamadas.push(`play:${this.src}`);
  }
  pause(): void {
    this.chamadas.push('pause');
  }
  load(): void {
    this.chamadas.push(`load:${this.src}`);
  }
  removeAttribute(nome: string): void {
    if (nome === 'src') this.src = '';
    this.chamadas.push(`remove:${nome}`);
  }
  addEventListener(tipo: string, ouvinte: () => void): void {
    this.ouvintes.set(tipo, [...(this.ouvintes.get(tipo) ?? []), ouvinte]);
  }
  disparar(tipo: 'playing' | 'ended' | 'error'): void {
    for (const ouvinte of this.ouvintes.get(tipo) ?? []) ouvinte();
  }
}

function montar() {
  const audios: AudioFalso[] = [];
  let relogio = 0;
  const vigias: { fn: () => void; cancelado: boolean }[] = [];
  const travados: number[] = [];
  let ultimo: EstadoDaFila | null = null;
  const fila = criarFila({
    criarAudio: () => {
      const a = new AudioFalso();
      audios.push(a);
      return a;
    },
    agora: () => relogio,
    agendar: (fn) => {
      const vigia = { fn, cancelado: false };
      vigias.push(vigia);
      return () => {
        vigia.cancelado = true;
      };
    },
    aoMudar: (e) => {
      ultimo = e;
    },
    aoTravar: (i) => travados.push(i),
  });
  return {
    fila,
    audios,
    travados,
    avancar: (ms: number) => {
      relogio += ms;
    },
    estourarVigias: () => {
      for (const v of vigias) if (!v.cancelado) v.fn();
    },
    estado: () => ultimo,
  };
}

const trecho = (index: number) => ({ index, url: `https://media/${index}.aac` });

describe('filaDePlayback', () => {
  it('toca em ordem de índice, mesmo com o 1 chegando antes do 0', () => {
    const m = montar();

    m.fila.enfileirar(trecho(1));
    expect(m.fila.estado().tocando).toBeNull();
    m.fila.enfileirar(trecho(0));

    expect(m.fila.estado().tocando).toBe(0);
    // O elemento do 1 já existia e já tinha começado a carregar: prefetch.
    expect(m.audios[0]?.chamadas).toContain('load:https://media/1.aac');
  });

  it('descarta trecho repetido (histórico + ao vivo)', () => {
    const m = montar();
    m.fila.enfileirar(trecho(0));
    m.fila.enfileirar(trecho(0));
    expect(m.audios).toHaveLength(1);
  });

  it('mede o gap do fim do 0 ao som do 1, e o primeiro instante audível', () => {
    const m = montar();
    m.fila.enfileirar(trecho(0));
    m.fila.enfileirar(trecho(1));
    const [a0, a1] = m.audios;

    m.avancar(100);
    a0?.disparar('playing');
    m.avancar(1500);
    a0?.disparar('ended');
    m.avancar(40);
    a1?.disparar('playing');

    const estado = m.estado();
    expect(estado?.primeiroAudivelEm).toBe(100);
    expect(estado?.gaps).toEqual([40]);
    expect(estado?.concluidos).toEqual([0]);
    expect(estado?.tocando).toBe(1);
  });

  it('trecho que não fica audível no prazo é reportado como travado', () => {
    const m = montar();
    m.fila.enfileirar(trecho(0));

    m.estourarVigias();

    expect(m.travados).toEqual([0]);
  });

  it('renovar troca o elemento do trecho travado e volta a tocar', () => {
    const m = montar();
    m.fila.enfileirar(trecho(0));
    const velho = m.audios[0];

    m.fila.renovar({ index: 0, url: 'https://media/0-novo.aac' });

    expect(velho?.chamadas).toContain('pause');
    expect(m.audios[1]?.chamadas).toContain('play:https://media/0-novo.aac');
  });

  it('limpar PAUSA antes de soltar (LEARNING-0006) e ignora eventos atrasados', () => {
    const m = montar();
    m.fila.enfileirar(trecho(0));
    const a0 = m.audios[0];

    m.fila.limpar();
    a0?.disparar('playing');

    const chamadas = a0?.chamadas ?? [];
    expect(chamadas.indexOf('pause')).toBeLessThan(chamadas.indexOf('remove:src'));
    expect(m.fila.estado().tocando).toBeNull();
    expect(m.fila.estado().primeiroAudivelEm).toBeNull();
  });
});
