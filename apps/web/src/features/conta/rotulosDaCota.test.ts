import { describe, expect, it } from 'vitest';

import {
  fracaoUsada,
  mensagemDeBloqueio,
  rotuloDaVirada,
  rotuloDoSaldo,
} from './rotulosDaCota';

describe('rotulosDaCota', () => {
  it('mostra minutos inteiros e nunca passa do teto', () => {
    expect(rotuloDoSaldo({ spoken_seconds: 259, quota_spoken_seconds: 600 })).toBe(
      '4 de 10 min',
    );
    expect(rotuloDoSaldo({ spoken_seconds: 700, quota_spoken_seconds: 600 })).toBe(
      '10 de 10 min',
    );
  });

  it('a barra fica entre 0 e 1', () => {
    expect(fracaoUsada({ spoken_seconds: 300, quota_spoken_seconds: 600 })).toBe(0.5);
    expect(fracaoUsada({ spoken_seconds: 900, quota_spoken_seconds: 600 })).toBe(1);
    expect(fracaoUsada({ spoken_seconds: 0, quota_spoken_seconds: 0 })).toBe(1);
  });

  it('a virada sai no relógio local, sem zero à esquerda na hora', () => {
    const local = new Date(2026, 9, 2, 0, 0);
    expect(rotuloDaVirada(local.toISOString())).toBe('Renova às 0:00');
  });

  it('cada motivo de bloqueio tem a sua frase, e null é "pode falar"', () => {
    expect(mensagemDeBloqueio(null)).toBeNull();
    const frases = new Set(
      (['daily_minutes', 'many_short_turns', 'service_paused'] as const).map(
        mensagemDeBloqueio,
      ),
    );
    expect(frases.size).toBe(3);
  });
});
