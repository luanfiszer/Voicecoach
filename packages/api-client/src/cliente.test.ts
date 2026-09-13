/**
 * `criarCliente`: a costura testável do ADR-0046 — `fetch` injetado, sem
 * framework de mock. O primeiro teste deste pacote, e ele exercita
 * `listarSessoes` (CARD-029/030) porque é o método mais novo, mas a técnica
 * vale para qualquer um: um `fetch` fake que grava a chamada e devolve um
 * `Response` de verdade (`Response` do `undici`/Node é global desde o
 * Node 18, o mesmo runtime do Vitest aqui).
 */

import { describe, expect, it } from 'vitest';

import { criarCliente, ErroDaApi, ErroDeRede } from './cliente';

function fetchQueDevolve(
  corpo: unknown,
  init: ResponseInit = {},
): { fetch: typeof fetch; urls: string[] } {
  const urls: string[] = [];
  const fake: typeof fetch = async (url) => {
    urls.push(String(url));
    return new Response(JSON.stringify(corpo), {
      status: 200,
      headers: { 'content-type': 'application/json' },
      ...init,
    });
  };
  return { fetch: fake, urls };
}

describe('listarSessoes', () => {
  it('monta a URL sem query quando nenhuma janela é pedida', async () => {
    const { fetch, urls } = fetchQueDevolve({ sessions: [], window_days: 30 });
    const cliente = criarCliente({ baseUrl: 'http://api.local', fetch });

    await cliente.listarSessoes();

    expect(urls).toEqual(['http://api.local/v1/sessions']);
  });

  it('manda `days` como query quando a janela é explícita', async () => {
    const { fetch, urls } = fetchQueDevolve({ sessions: [], window_days: 7 });
    const cliente = criarCliente({ baseUrl: 'http://api.local', fetch });

    await cliente.listarSessoes(7);

    expect(urls).toEqual(['http://api.local/v1/sessions?days=7']);
  });

  it('devolve o envelope inteiro, tipado', async () => {
    const envelope = {
      sessions: [
        {
          id: '11111111-1111-1111-1111-111111111111',
          started_at: '2026-09-13T12:00:00Z',
          ended_at: null,
          spoken_seconds: 492,
          turns: 7,
          corrections: 5,
          reply_media_available: true,
        },
      ],
      window_days: 30,
    };
    const cliente = criarCliente({
      baseUrl: 'http://api.local',
      fetch: fetchQueDevolve(envelope).fetch,
    });

    const resultado = await cliente.listarSessoes();

    expect(resultado).toEqual(envelope);
  });

  it('um 4xx vira ErroDaApi com o `detail` do Problem Details', async () => {
    const { fetch } = fetchQueDevolve(
      { title: 'Não encontrado', detail: 'sem sessão' },
      { status: 404 },
    );
    const cliente = criarCliente({ baseUrl: 'http://api.local', fetch });

    await expect(cliente.listarSessoes()).rejects.toMatchObject({
      status: 404,
      detalhe: 'sem sessão',
    });
    await expect(cliente.listarSessoes()).rejects.toBeInstanceOf(ErroDaApi);
  });

  it('a URN do Problem Details vira `tipo` — a chave que o CARD-027 compara', async () => {
    const { fetch } = fetchQueDevolve(
      {
        type: 'urn:voicecoach:problem:daily-quota-exceeded',
        title: 'Cota diária esgotada',
        detail: 'renova à meia-noite',
      },
      { status: 429 },
    );
    const cliente = criarCliente({ baseUrl: 'http://api.local', fetch });

    await expect(cliente.listarSessoes()).rejects.toMatchObject({
      tipo: 'urn:voicecoach:problem:daily-quota-exceeded',
    });
  });

  it('falha de transporte vira ErroDeRede nomeando o host', async () => {
    const semRede: typeof fetch = async () => {
      throw new TypeError('fetch failed');
    };
    const cliente = criarCliente({ baseUrl: 'http://api.local', fetch: semRede });

    await expect(cliente.listarSessoes()).rejects.toBeInstanceOf(ErroDeRede);
    await expect(cliente.listarSessoes()).rejects.toMatchObject({
      host: 'http://api.local',
    });
  });
});

describe('descartarTurn', () => {
  it('faz POST em /turns/{id}/discard e não tenta ler corpo em 204', async () => {
    const urls: string[] = [];
    const metodos: (string | undefined)[] = [];
    const fake: typeof fetch = async (url, init) => {
      urls.push(String(url));
      metodos.push(init?.method);
      return new Response(null, { status: 204 });
    };
    const cliente = criarCliente({ baseUrl: 'http://api.local', fetch: fake });

    await cliente.descartarTurn('11111111-1111-1111-1111-111111111111');

    expect(urls).toEqual([
      'http://api.local/v1/turns/11111111-1111-1111-1111-111111111111/discard',
    ]);
    expect(metodos).toEqual(['POST']);
  });

  it('turn já concluído (409) vira ErroDaApi com a URN certa', async () => {
    const { fetch } = fetchQueDevolve(
      {
        type: 'urn:voicecoach:problem:turn-already-completed',
        title: 'Turno já concluído',
      },
      { status: 409 },
    );
    const cliente = criarCliente({ baseUrl: 'http://api.local', fetch });

    await expect(cliente.descartarTurn('id')).rejects.toMatchObject({
      status: 409,
      tipo: 'urn:voicecoach:problem:turn-already-completed',
    });
  });
});
