import { ErroDaApi, ErroDeRede } from '@voicecoach/api-client';
import { describe, expect, it } from 'vitest';

import { excecaoDoErro } from './excecoes';

describe('excecaoDoErro', () => {
  it('a URN decide; o texto do servidor é o corpo', () => {
    const cota = new ErroDaApi(
      429,
      'Cota diária esgotada',
      'Renova à meia-noite.',
      'urn:voicecoach:problem:daily-quota-exceeded',
    );
    expect(excecaoDoErro(cota)).toEqual({
      tipo: 'cota',
      mensagem: 'Renova à meia-noite.',
    });
  });

  it('falha de transporte é "offline"; outro erro da API não tem tela própria', () => {
    expect(excecaoDoErro(new ErroDeRede('', new Error('x')))?.tipo).toBe('offline');
    expect(excecaoDoErro(new ErroDaApi(422, 'x', null, 'urn:outra'))).toBeNull();
  });
});
