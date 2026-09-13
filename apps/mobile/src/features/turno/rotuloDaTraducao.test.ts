import { describe, expect, it } from 'vitest';

import { rotuloDoBotaoDeTraduzir } from './rotuloDaTraducao';

describe('rotuloDoBotaoDeTraduzir', () => {
  it('convida a traduzir quando ocioso', () => {
    expect(rotuloDoBotaoDeTraduzir('ocioso')).toBe('TRADUZIR');
  });

  it('avisa que está em andamento', () => {
    expect(rotuloDoBotaoDeTraduzir('traduzindo')).toBe('TRADUZINDO…');
  });

  it('convida a tentar de novo quando falhou', () => {
    expect(rotuloDoBotaoDeTraduzir('falhou')).toBe(
      'TRADUÇÃO FALHOU — TOCAR PARA TENTAR DE NOVO',
    );
  });
});
