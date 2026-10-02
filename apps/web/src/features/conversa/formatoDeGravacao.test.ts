import { describe, expect, it } from 'vitest';

import { escolherFormato, tipoDoUpload } from './formatoDeGravacao';

describe('escolherFormato', () => {
  it('Chrome/Firefox: WebM com Opus', () => {
    const chrome = (tipo: string) => tipo.startsWith('audio/webm');
    expect(escolherFormato(chrome)).toEqual({
      mimeType: 'audio/webm;codecs=opus',
      extensao: 'webm',
    });
  });

  it('Safari: só MP4, e o arquivo vai como .m4a', () => {
    const safari = (tipo: string) => tipo === 'audio/mp4';
    expect(escolherFormato(safari)?.extensao).toBe('m4a');
  });

  it('navegador sem nenhum formato: null, para a tela explicar', () => {
    expect(escolherFormato(() => false)).toBeNull();
  });
});

describe('tipoDoUpload', () => {
  it('usa o tipo real do gravador, com codecs, e cai no pedido se vier vazio', () => {
    const pedido = { mimeType: 'audio/mp4', extensao: 'm4a' } as const;
    expect(tipoDoUpload('audio/mp4;codecs=mp4a.40.2', pedido)).toBe(
      'audio/mp4;codecs=mp4a.40.2',
    );
    expect(tipoDoUpload('', pedido)).toBe('audio/mp4');
  });
});
