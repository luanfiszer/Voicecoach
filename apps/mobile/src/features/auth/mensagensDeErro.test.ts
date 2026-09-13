import { ErroDaApi, ErroDeRede } from '@voicecoach/api-client';
import { describe, expect, it } from 'vitest';

import { mensagemDeErroDeAuth } from './mensagensDeErro';

describe('mensagemDeErroDeAuth', () => {
  it('credenciais inválidas tem mensagem própria', () => {
    const erro = new ErroDaApi(
      401,
      'Credenciais inválidas',
      null,
      'urn:voicecoach:problem:invalid-credentials',
    );
    expect(mensagemDeErroDeAuth(erro)).toBe('E-mail ou senha incorretos.');
  });

  it('rate limit tem mensagem própria', () => {
    const erro = new ErroDaApi(
      429,
      'Muitas requisições',
      null,
      'urn:voicecoach:problem:rate-limited',
    );
    expect(mensagemDeErroDeAuth(erro)).toBe(
      'Muitas tentativas seguidas. Espere um pouco e tente de novo.',
    );
  });

  it('outro ErroDaApi usa o detalhe do Problem Details', () => {
    const erro = new ErroDaApi(
      400,
      'Link inválido',
      'Este link não é válido ou já expirou.',
      'urn:voicecoach:problem:invalid-password-reset-token',
    );
    expect(mensagemDeErroDeAuth(erro)).toBe('Este link não é válido ou já expirou.');
  });

  it('ErroDeRede tem mensagem de conectividade', () => {
    const erro = new ErroDeRede('http://api.local', new Error('fetch failed'));
    expect(mensagemDeErroDeAuth(erro)).toBe(
      'Não foi possível falar com o servidor. Verifique sua conexão.',
    );
  });

  it('qualquer outra coisa cai no genérico', () => {
    expect(mensagemDeErroDeAuth('lixo')).toBe('Algo deu errado. Tente de novo.');
  });
});
