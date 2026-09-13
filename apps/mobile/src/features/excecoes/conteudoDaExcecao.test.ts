/**
 * Cada asserção corresponde a um critério de aceite do CARD-027: a URN
 * discrimina a tela, a mensagem, não o texto ou o status HTTP sozinho.
 */

import { ErroDaApi, ErroDeRede } from '@voicecoach/api-client';
import { describe, expect, it } from 'vitest';
import {
  conteudoDoErro,
  conteudoDoTravamento,
  mensagemDeTravamento,
  URN_COTA_DIARIA_ESGOTADA,
  URN_SERVICO_PAUSADO,
} from './conteudoDaExcecao';

describe('conteudoDoErro', () => {
  it('ErroDeRede vira a tela offline, sem depender de status nenhum', () => {
    const erro = new ErroDeRede(
      'http://192.168.0.1:8000',
      new TypeError('fetch failed'),
    );

    expect(conteudoDoErro(erro)).toEqual({ tipo: 'offline' });
  });

  it('a URN de cota vira a tela de cota — mesma URN do backend, ADR-0063', () => {
    const erro = new ErroDaApi(
      429,
      'Cota diária esgotada',
      'renova à meia-noite',
      URN_COTA_DIARIA_ESGOTADA,
    );

    expect(conteudoDoErro(erro)).toEqual({
      tipo: 'cota',
      mensagem: 'renova à meia-noite',
    });
  });

  it('a URN de kill switch vira a tela de pausado, distinta da de cota', () => {
    const erro = new ErroDaApi(
      503,
      'Serviço pausado',
      'tente mais tarde',
      URN_SERVICO_PAUSADO,
    );

    const conteudo = conteudoDoErro(erro);
    expect(conteudo).toEqual({ tipo: 'pausado', mensagem: 'tente mais tarde' });
    // As duas URNs produzem telas DIFERENTES — é o ponto central do card.
    expect(conteudo?.tipo).not.toBe(
      conteudoDoErro(new ErroDaApi(429, 'x', null, URN_COTA_DIARIA_ESGOTADA))?.tipo,
    );
  });

  it('sem `detail` do servidor, cai na mensagem padrão — nunca em branco', () => {
    const erro = new ErroDaApi(
      429,
      'Cota diária esgotada',
      null,
      URN_COTA_DIARIA_ESGOTADA,
    );

    const conteudo = conteudoDoErro(erro);
    expect(conteudo?.tipo).toBe('cota');
    expect(conteudo && 'mensagem' in conteudo ? conteudo.mensagem : '').not.toBe('');
  });

  it('uma URN desconhecida (ou nenhuma) não vira tela própria — cai no fallback existente', () => {
    const semUrn = new ErroDaApi(422, 'Áudio inválido', 'formato não suportado', null);
    const urnEstranha = new ErroDaApi(
      404,
      'Turno não encontrado',
      null,
      'urn:voicecoach:problem:turn-not-found',
    );

    expect(conteudoDoErro(semUrn)).toBeNull();
    expect(conteudoDoErro(urnEstranha)).toBeNull();
  });

  it('um erro que não é nem ErroDaApi nem ErroDeRede também é null', () => {
    expect(conteudoDoErro(new Error('algo genérico'))).toBeNull();
    expect(conteudoDoErro('string qualquer')).toBeNull();
  });
});

describe('conteudoDoTravamento', () => {
  it('carrega o turnId — é ele que "Descartar" precisa para chamar o servidor', () => {
    expect(conteudoDoTravamento('abc-123', 30)).toEqual({
      tipo: 'travado',
      turnId: 'abc-123',
      segundos: 30,
    });
  });
});

describe('mensagemDeTravamento', () => {
  it('usa o prazo CONFIGURADO, não "30s" fixo no texto', () => {
    expect(mensagemDeTravamento(30)).toMatch(/30s/);
    expect(mensagemDeTravamento(45)).toMatch(/45s/);
    expect(mensagemDeTravamento(45)).not.toMatch(/30s/);
  });
});
