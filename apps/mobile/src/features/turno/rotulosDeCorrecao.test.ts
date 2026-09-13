import { describe, expect, it } from 'vitest';

import {
  formatarResumo,
  RESUMO_VAZIO,
  rotuloDaSeveridade,
  rotuloDoTipo,
} from './rotulosDeCorrecao';

describe('rotuloDoTipo', () => {
  it('traduz os cinco tipos fechados do contrato', () => {
    expect(rotuloDoTipo('grammar')).toBe('Gramática');
    expect(rotuloDoTipo('vocabulary')).toBe('Vocabulário');
    expect(rotuloDoTipo('preposition')).toBe('Preposição');
    expect(rotuloDoTipo('word_order')).toBe('Ordem das palavras');
    expect(rotuloDoTipo('other')).toBe('Outro');
  });
});

describe('rotuloDaSeveridade', () => {
  it('traduz as três severidades', () => {
    expect(rotuloDaSeveridade('minor')).toBe('Leve');
    expect(rotuloDaSeveridade('moderate')).toBe('Moderado');
    expect(rotuloDaSeveridade('major')).toBe('Importante');
  });
});

describe('formatarResumo', () => {
  it('devolve null quando não há nenhuma correção — sem correção, sem ruído', () => {
    expect(formatarResumo(RESUMO_VAZIO)).toBeNull();
  });

  it('usa singular para uma correção só', () => {
    const resumo = { total: 1, porTipo: { grammar: 1 } };
    expect(formatarResumo(resumo)).toBe('1 correção: 1 Gramática');
  });

  it('ordena por contagem decrescente, e por tipo em empate', () => {
    const resumo = {
      total: 5,
      porTipo: { other: 1, grammar: 2, vocabulary: 2 },
    };
    // grammar e vocabulary empatam em 2 — desempate alfabético do TIPO
    // ("grammar" < "vocabulary"), não da ordem em que apareceram no objeto.
    expect(formatarResumo(resumo)).toBe(
      '5 correções: 2 Gramática, 2 Vocabulário, 1 Outro',
    );
  });

  it('a mesma sessão não muda de texto dependendo da ordem de chegada', () => {
    const a = { total: 2, porTipo: { other: 1, grammar: 1 } };
    const b = { total: 2, porTipo: { grammar: 1, other: 1 } };
    expect(formatarResumo(a)).toBe(formatarResumo(b));
  });
});
