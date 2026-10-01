/**
 * A sessão da web (CARD-064, ADR-0077), com o critério de aceite mais caro:
 * duas abas que renovam ao mesmo tempo continuam logadas.
 *
 * O servidor falso reproduz o que o backend faz desde o CARD-064 (rotação
 * atômica + detecção de reuso), e o "pote de cookies" é compartilhado entre
 * as sessões — exatamente como o navegador compartilha o cookie entre abas.
 */

import { ErroDaApi, type TokenDeAcesso } from '@voicecoach/api-client';
import { describe, expect, it } from 'vitest';

import {
  type ClienteDeAuthWeb,
  criarSessaoWeb,
  type Trava,
  travaDoNavegador,
} from './sessaoWeb';

/** O navegador + o backend, do ponto de vista do refresh. */
function criarMundo() {
  let geracao = 0;
  let valido: string | null = null;
  const pote = { cookie: null as string | null };
  const chamadasDeRenovacao: string[] = [];

  function abrirSessao(): TokenDeAcesso {
    geracao += 1;
    valido = `refresh-${geracao}`;
    pote.cookie = valido;
    return { access_token: `access-${geracao}`, token_type: 'bearer', expires_in: 900 };
  }

  async function renovarSessaoWeb(): Promise<TokenDeAcesso> {
    // O navegador anexa o cookie no instante em que a requisição SAI…
    const enviado = pote.cookie;
    chamadasDeRenovacao.push(enviado ?? '(sem cookie)');
    // …e a resposta volta depois de uma ida e volta de rede.
    await new Promise((resolver) => setTimeout(resolver, 5));
    if (enviado === null || enviado !== valido) {
      // Reuso (ou cookie de uma família morta): o servidor revoga tudo.
      valido = null;
      throw new ErroDaApi(401, 'Refresh token inválido', null, null);
    }
    return abrirSessao();
  }

  function cliente(): ClienteDeAuthWeb {
    return {
      loginWeb: async () => abrirSessao(),
      loginGoogleWeb: async () => abrirSessao(),
      renovarSessaoWeb,
      sairDaWeb: async () => {
        valido = null;
        pote.cookie = null;
      },
      registrar: async () => {},
      confirmarEmail: async () => {},
      reenviarConfirmacao: async () => {},
      pedirRedefinicaoDeSenha: async () => {},
      redefinirSenha: async () => {},
    };
  }

  return {
    cliente,
    abrirSessao,
    pote,
    chamadasDeRenovacao,
    familiaViva: () => valido !== null,
  };
}

/** A Web Locks API de mentirinha: uma fila por nome, compartilhada pelas abas. */
function travaCompartilhada(): Trava {
  const filas = new Map<string, Promise<unknown>>();
  return (nome, fn) => {
    const anterior = filas.get(nome) ?? Promise.resolve();
    const minha = anterior.then(fn, fn);
    filas.set(
      nome,
      minha.catch(() => undefined),
    );
    return minha;
  };
}

const semTrava: Trava = (_nome, fn) => fn();

describe('duas abas renovando ao mesmo tempo (o critério do ADR-0077)', () => {
  it('com a trava entre abas, as DUAS continuam logadas', async () => {
    const mundo = criarMundo();
    mundo.abrirSessao(); // o aluno entrou antes; as duas abas só têm o cookie
    const trava = travaCompartilhada();
    const abaA = criarSessaoWeb({ cliente: mundo.cliente(), trava });
    const abaB = criarSessaoWeb({ cliente: mundo.cliente(), trava });

    await Promise.all([abaA.inicializar(), abaB.inicializar()]);

    expect(abaA.obterEstado()).toBe('autenticado');
    expect(abaB.obterEstado()).toBe('autenticado');
    expect(mundo.familiaViva()).toBe(true);
    // A segunda aba mandou o cookie JÁ rotacionado pela primeira.
    expect(mundo.chamadasDeRenovacao).toEqual(['refresh-1', 'refresh-2']);
  });

  it('sem a trava, o servidor vê reuso e a família morre (por que a trava existe)', async () => {
    const mundo = criarMundo();
    mundo.abrirSessao();
    const abaA = criarSessaoWeb({ cliente: mundo.cliente(), trava: semTrava });
    const abaB = criarSessaoWeb({ cliente: mundo.cliente(), trava: semTrava });

    await Promise.all([abaA.inicializar(), abaB.inicializar()]);

    expect(mundo.chamadasDeRenovacao).toEqual(['refresh-1', 'refresh-1']);
    expect(mundo.familiaViva()).toBe(false);
    expect([abaA.obterEstado(), abaB.obterEstado()]).toContain('nao_autenticado');
  });
});

describe('uma aba só', () => {
  it('inicializar sem cookie termina deslogado, sem erro', async () => {
    const mundo = criarMundo();
    const sessao = criarSessaoWeb({ cliente: mundo.cliente(), trava: semTrava });

    await sessao.inicializar();

    expect(sessao.obterEstado()).toBe('nao_autenticado');
  });

  it('fetchAutenticado injeta o Bearer e, num 401, renova e repete uma vez', async () => {
    const mundo = criarMundo();
    const cabecalhosVistos: (string | null)[] = [];
    let respostas = [401, 200];
    const fetchCru: typeof fetch = async (_url, init) => {
      cabecalhosVistos.push(new Headers(init?.headers).get('Authorization'));
      const [status, ...resto] = respostas;
      respostas = resto;
      return new Response(null, { status: status ?? 200 });
    };
    const sessao = criarSessaoWeb({
      cliente: mundo.cliente(),
      trava: semTrava,
      fetchCru,
    });
    await sessao.login('a@b.com', 'senha-forte');

    const resposta = await sessao.fetchAutenticado('/v1/sessions');

    expect(resposta.status).toBe(200);
    expect(cabecalhosVistos).toEqual(['Bearer access-1', 'Bearer access-2']);
  });

  it('sair desloga mesmo se o servidor não responder', async () => {
    const mundo = criarMundo();
    const cliente = {
      ...mundo.cliente(),
      sairDaWeb: () => Promise.reject(new Error('rede')),
    };
    const sessao = criarSessaoWeb({ cliente, trava: semTrava });
    await sessao.login('a@b.com', 'senha-forte');

    await sessao.sair();

    expect(sessao.obterEstado()).toBe('nao_autenticado');
  });
});

describe('travaDoNavegador', () => {
  it('sem Web Locks API, roda direto (recuo documentado)', async () => {
    const trava = travaDoNavegador(undefined);

    expect(await trava('x', async () => 42)).toBe(42);
  });
});
