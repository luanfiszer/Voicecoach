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

describe('traduzirTexto', () => {
  it('faz POST em /turns/{id}/translations com o alvo e o índice no corpo', async () => {
    const urls: string[] = [];
    const corpos: string[] = [];
    const fake: typeof fetch = async (url, init) => {
      urls.push(String(url));
      corpos.push(String(init?.body));
      return new Response(JSON.stringify({ text: 'Olá, aluno.', cached: false }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
    };
    const cliente = criarCliente({ baseUrl: 'http://api.local', fetch: fake });

    const traducao = await cliente.traduzirTexto(
      '11111111-1111-1111-1111-111111111111',
      'reply',
    );

    expect(urls).toEqual([
      'http://api.local/v1/turns/11111111-1111-1111-1111-111111111111/translations',
    ]);
    expect(JSON.parse(corpos[0] ?? '')).toEqual({ target: 'reply', index: 0 });
    expect(traducao).toEqual({ text: 'Olá, aluno.', cached: false });
  });

  it('manda o índice explícito para uma correção', async () => {
    const corpos: string[] = [];
    const fake: typeof fetch = async (_url, init) => {
      corpos.push(String(init?.body));
      return new Response(
        JSON.stringify({ text: 'Correção em português.', cached: true }),
        {
          status: 200,
          headers: { 'content-type': 'application/json' },
        },
      );
    };
    const cliente = criarCliente({ baseUrl: 'http://api.local', fetch: fake });

    await cliente.traduzirTexto('id-do-turn', 'correction', 2);

    expect(JSON.parse(corpos[0] ?? '')).toEqual({ target: 'correction', index: 2 });
  });

  it('endpoint indisponível vira ErroDaApi com o `detail` do Problem Details', async () => {
    const { fetch } = fetchQueDevolve(
      { title: 'Não encontrado', detail: 'turn sem resposta ainda' },
      { status: 404 },
    );
    const cliente = criarCliente({ baseUrl: 'http://api.local', fetch });

    await expect(cliente.traduzirTexto('id', 'reply')).rejects.toMatchObject({
      status: 404,
      detalhe: 'turn sem resposta ainda',
    });
  });
});

describe('registrar', () => {
  it('faz POST em /auth/register com e-mail e senha', async () => {
    const urls: string[] = [];
    const corpos: string[] = [];
    const fake: typeof fetch = async (url, init) => {
      urls.push(String(url));
      corpos.push(String(init?.body));
      return new Response(null, { status: 202 });
    };
    const cliente = criarCliente({ baseUrl: 'http://api.local', fetch: fake });

    await cliente.registrar('aluno@example.com', 'senha-super-secreta');

    expect(urls).toEqual(['http://api.local/v1/auth/register']);
    expect(JSON.parse(corpos[0] ?? '')).toEqual({
      email: 'aluno@example.com',
      password: 'senha-super-secreta',
    });
  });
});

describe('login', () => {
  it('devolve o par de tokens', async () => {
    const par = {
      access_token: 'access-abc',
      refresh_token: 'refresh-xyz',
      token_type: 'bearer',
      expires_in: 900,
    };
    const cliente = criarCliente({
      baseUrl: 'http://api.local',
      fetch: fetchQueDevolve(par).fetch,
    });

    const resultado = await cliente.login('aluno@example.com', 'senha-certa');

    expect(resultado).toEqual(par);
  });

  it('senha errada vira ErroDaApi 401', async () => {
    const { fetch } = fetchQueDevolve(
      {
        type: 'urn:voicecoach:problem:invalid-credentials',
        title: 'Credenciais inválidas',
      },
      { status: 401 },
    );
    const cliente = criarCliente({ baseUrl: 'http://api.local', fetch });

    await expect(
      cliente.login('aluno@example.com', 'senha-errada'),
    ).rejects.toMatchObject({ status: 401 });
  });
});

describe('renovarTokens', () => {
  it('manda o refresh token no corpo e devolve o par novo', async () => {
    const corpos: string[] = [];
    const novoPar = {
      access_token: 'access-novo',
      refresh_token: 'refresh-novo',
      token_type: 'bearer',
      expires_in: 900,
    };
    const fake: typeof fetch = async (_url, init) => {
      corpos.push(String(init?.body));
      return new Response(JSON.stringify(novoPar), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
    };
    const cliente = criarCliente({ baseUrl: 'http://api.local', fetch: fake });

    const resultado = await cliente.renovarTokens('refresh-antigo');

    expect(JSON.parse(corpos[0] ?? '')).toEqual({ refresh_token: 'refresh-antigo' });
    expect(resultado).toEqual(novoPar);
  });

  it('refresh inválido (reuso detectado) vira ErroDaApi 401', async () => {
    const { fetch } = fetchQueDevolve(
      {
        type: 'urn:voicecoach:problem:invalid-refresh-token',
        title: 'Refresh token inválido',
      },
      { status: 401 },
    );
    const cliente = criarCliente({ baseUrl: 'http://api.local', fetch });

    await expect(cliente.renovarTokens('refresh-reusado')).rejects.toMatchObject({
      status: 401,
    });
  });
});

describe('sair', () => {
  it('faz POST em /auth/logout com o refresh token', async () => {
    const urls: string[] = [];
    const corpos: string[] = [];
    const fake: typeof fetch = async (url, init) => {
      urls.push(String(url));
      corpos.push(String(init?.body));
      return new Response(null, { status: 204 });
    };
    const cliente = criarCliente({ baseUrl: 'http://api.local', fetch: fake });

    await cliente.sair('refresh-do-aluno');

    expect(urls).toEqual(['http://api.local/v1/auth/logout']);
    expect(JSON.parse(corpos[0] ?? '')).toEqual({
      refresh_token: 'refresh-do-aluno',
    });
  });
});

describe('confirmarEmail', () => {
  it('faz GET em /auth/confirm-email com o token na query', async () => {
    const urls: string[] = [];
    const fake: typeof fetch = async (url) => {
      urls.push(String(url));
      return new Response(JSON.stringify({ status: 'confirmed' }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
    };
    const cliente = criarCliente({ baseUrl: 'http://api.local', fetch: fake });

    await cliente.confirmarEmail('token-do-link');

    expect(urls).toEqual([
      'http://api.local/v1/auth/confirm-email?token=token-do-link',
    ]);
  });

  it('token inválido vira ErroDaApi 400', async () => {
    const { fetch } = fetchQueDevolve(
      { title: 'Link de confirmação inválido' },
      { status: 400 },
    );
    const cliente = criarCliente({ baseUrl: 'http://api.local', fetch });

    await expect(cliente.confirmarEmail('token-invalido')).rejects.toMatchObject({
      status: 400,
    });
  });
});

describe('reenviarConfirmacao', () => {
  it('faz POST em /auth/resend-confirmation com o e-mail', async () => {
    const corpos: string[] = [];
    const fake: typeof fetch = async (_url, init) => {
      corpos.push(String(init?.body));
      return new Response(null, { status: 202 });
    };
    const cliente = criarCliente({ baseUrl: 'http://api.local', fetch: fake });

    await cliente.reenviarConfirmacao('aluno@example.com');

    expect(JSON.parse(corpos[0] ?? '')).toEqual({ email: 'aluno@example.com' });
  });
});

describe('pedirRedefinicaoDeSenha', () => {
  it('faz POST em /auth/request-password-reset com o e-mail', async () => {
    const corpos: string[] = [];
    const fake: typeof fetch = async (_url, init) => {
      corpos.push(String(init?.body));
      return new Response(null, { status: 202 });
    };
    const cliente = criarCliente({ baseUrl: 'http://api.local', fetch: fake });

    await cliente.pedirRedefinicaoDeSenha('aluno@example.com');

    expect(JSON.parse(corpos[0] ?? '')).toEqual({ email: 'aluno@example.com' });
  });
});

describe('redefinirSenha', () => {
  it('faz POST em /auth/reset-password com o token e a senha nova', async () => {
    const corpos: string[] = [];
    const fake: typeof fetch = async (_url, init) => {
      corpos.push(String(init?.body));
      return new Response(null, { status: 200 });
    };
    const cliente = criarCliente({ baseUrl: 'http://api.local', fetch: fake });

    await cliente.redefinirSenha('token-do-reset', 'senha-nova-123');

    expect(JSON.parse(corpos[0] ?? '')).toEqual({
      token: 'token-do-reset',
      new_password: 'senha-nova-123',
    });
  });

  it('token inválido vira ErroDaApi 400', async () => {
    const { fetch } = fetchQueDevolve(
      { title: 'Link de redefinição inválido' },
      { status: 400 },
    );
    const cliente = criarCliente({ baseUrl: 'http://api.local', fetch });

    await expect(
      cliente.redefinirSenha('token-invalido', 'senha-nova-123'),
    ).rejects.toMatchObject({ status: 400 });
  });
});

describe('excluirConta', () => {
  it('faz DELETE em /students/me, sem corpo', async () => {
    const urls: string[] = [];
    const metodos: string[] = [];
    const fake: typeof fetch = async (url, init) => {
      urls.push(String(url));
      metodos.push(String(init?.method));
      return new Response(null, { status: 204 });
    };
    const cliente = criarCliente({ baseUrl: 'http://api.local', fetch: fake });

    await cliente.excluirConta();

    expect(urls).toEqual(['http://api.local/v1/students/me']);
    expect(metodos).toEqual(['DELETE']);
  });

  it('limite de exclusões excedido vira ErroDaApi 429', async () => {
    const { fetch } = fetchQueDevolve({ title: 'Muitas requisições' }, { status: 429 });
    const cliente = criarCliente({ baseUrl: 'http://api.local', fetch });

    await expect(cliente.excluirConta()).rejects.toMatchObject({ status: 429 });
  });
});
