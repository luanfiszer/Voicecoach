import { describe, expect, it } from 'vitest';

import { rotuloDoLimiteDeGravacao } from './rotulosDeConfiguracoes';

describe('rotuloDoLimiteDeGravacao', () => {
  it('formata só segundos quando menor que um minuto', () => {
    expect(rotuloDoLimiteDeGravacao(45)).toBe('45 s');
  });

  it('formata minutos e segundos quando os dois existem', () => {
    expect(rotuloDoLimiteDeGravacao(90)).toBe('1 min 30 s');
  });

  it('formata só minutos quando o resto é exato', () => {
    expect(rotuloDoLimiteDeGravacao(120)).toBe('2 min');
  });
});
