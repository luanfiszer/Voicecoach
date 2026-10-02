import { describe, expect, it } from 'vitest';

import {
  formatarRelogio,
  type MotivoDeRecusa,
  mensagemDeRecusa,
  rotuloDoTipo,
  subtitulo,
} from './rotulosDaConversa';

describe('rotulosDaConversa', () => {
  it('cada motivo de recusa tem sua frase, sempre como convite (pergunta)', () => {
    const motivos: MotivoDeRecusa[] = ['low_confidence', 'no_speech', 'not_english'];
    const frases = motivos.map(mensagemDeRecusa);
    expect(new Set(frases).size).toBe(3);
    for (const frase of frases) expect(frase.endsWith('?')).toBe(true);
  });

  it('o rótulo do tipo de correção é o mesmo do mobile', () => {
    expect(rotuloDoTipo('word_order')).toBe('Ordem das palavras');
  });

  it('gravando manda no subtítulo, qualquer que seja o estado do turn', () => {
    expect(subtitulo(true, 'ouvindo')).toBe('Gravando… clique de novo para enviar.');
    expect(subtitulo(false, 'ouvindo')).toBe('O professor está respondendo.');
  });

  it('relógio m:ss', () => {
    expect(formatarRelogio(7.9)).toBe('0:07');
    expect(formatarRelogio(90)).toBe('1:30');
  });
});
