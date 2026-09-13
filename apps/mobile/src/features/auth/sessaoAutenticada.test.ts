import { describe, expect, it } from 'vitest';

import {
  type ArmazenamentoDeSessao,
  type ClienteDeAuth,
  criarSessaoAutenticada,
  type EstadoDaSessao,
} from './sessaoAutenticada';

const PAR_INICIAL = {
  access_token: 'access-1',
  refresh_token: 'refresh-1',
  token_type: 'bearer',
  expires_in: 900,
};

const PAR_RENOVADO = {
  access_token: 'access-2',
  refresh_token: 'refresh-2',
  token_type: 'bearer',
  expires_in: 900,
};

function armazenamentoFalso(
  refreshInicial: string | null = null,
): ArmazenamentoDeSessao & {
  token: string | null;
} {
  return {
    token: refreshInicial,
    async obterRefreshToken() {
      return this.token;
    },
    async definirRefreshToken(token: string) {
      this.token = token;
    },
    async limparRefreshToken() {
      this.token = null;
    },
  };
}

function clienteFalso(
  overrides: Partial<ClienteDeAuth> = {},
): ClienteDeAuth & { chamadas: Record<string, number> } {
  const chamadas: Record<string, number> = {};
  const conta = (nome: string) => {
    chamadas[nome] = (chamadas[nome] ?? 0) + 1;
  };
  return {
    chamadas,
    async login() {
      conta('login');
      return PAR_INICIAL;
    },
    async registrar() {
      conta('registrar');
    },
    async renovarTokens() {
      conta('renovarTokens');
      return PAR_RENOVADO;
    },
    async sair() {
      conta('sair');
    },
    async confirmarEmail() {
      conta('confirmarEmail');
    },
    async reenviarConfirmacao() {
      conta('reenviarConfirmacao');
    },
    async pedirRedefinicaoDeSenha() {
      conta('pedirRedefinicaoDeSenha');
    },
    async redefinirSenha() {
      conta('redefinirSenha');
    },
    ...overrides,
  };
}

describe('inicializar', () => {
  it('sem refresh guardado, o estado vai direto para não-autenticado', async () => {
    const armazenamento = armazenamentoFalso(null);
    const cliente = clienteFalso();
    const sessao = criarSessaoAutenticada({ cliente, armazenamento });

    await sessao.inicializar();

    expect(sessao.obterEstado()).toBe('nao_autenticado');
    expect(cliente.chamadas.renovarTokens).toBeUndefined();
  });

  it('com refresh válido guardado, renova e entra autenticado (login silencioso)', async () => {
    const armazenamento = armazenamentoFalso('refresh-do-boot-anterior');
    const cliente = clienteFalso();
    const sessao = criarSessaoAutenticada({ cliente, armazenamento });

    await sessao.inicializar();

    expect(sessao.obterEstado()).toBe('autenticado');
    expect(cliente.chamadas.renovarTokens).toBe(1);
    expect(armazenamento.token).toBe('refresh-2');
  });

  it('com refresh inválido, limpa o armazenamento e não deixa nada do aluno anterior', async () => {
    const armazenamento = armazenamentoFalso('refresh-expirado');
    const cliente = clienteFalso({
      async renovarTokens() {
        throw new Error('refresh token inválido');
      },
    });
    const sessao = criarSessaoAutenticada({ cliente, armazenamento });

    await sessao.inicializar();

    expect(sessao.obterEstado()).toBe('nao_autenticado');
    expect(armazenamento.token).toBeNull();
  });
});

describe('login', () => {
  it('aplica o par de tokens e guarda o refresh', async () => {
    const armazenamento = armazenamentoFalso();
    const cliente = clienteFalso();
    const sessao = criarSessaoAutenticada({ cliente, armazenamento });

    await sessao.login('aluno@example.com', 'senha-certa');

    expect(sessao.obterEstado()).toBe('autenticado');
    expect(armazenamento.token).toBe('refresh-1');
  });
});

describe('sair', () => {
  it('limpa o armazenamento e avisa o servidor com o refresh que tinha', async () => {
    const armazenamento = armazenamentoFalso('refresh-1');
    const cliente = clienteFalso();
    let refreshRecebido: string | undefined;
    const sessao = criarSessaoAutenticada({
      cliente: {
        ...cliente,
        async sair(refreshToken: string) {
          refreshRecebido = refreshToken;
        },
      },
      armazenamento,
    });

    await sessao.sair();

    expect(sessao.obterEstado()).toBe('nao_autenticado');
    expect(armazenamento.token).toBeNull();
    expect(refreshRecebido).toBe('refresh-1');
  });

  it('não propaga falha do servidor — o objetivo é destravar a tela na hora', async () => {
    const armazenamento = armazenamentoFalso('refresh-1');
    const cliente = clienteFalso({
      async sair() {
        throw new Error('rede fora');
      },
    });
    const sessao = criarSessaoAutenticada({ cliente, armazenamento });

    await expect(sessao.sair()).resolves.toBeUndefined();
    expect(armazenamento.token).toBeNull();
  });
});

describe('fetchAutenticado', () => {
  it('injeta o Authorization com o access token atual', async () => {
    const armazenamento = armazenamentoFalso();
    const cliente = clienteFalso();
    const sessao = criarSessaoAutenticada({ cliente, armazenamento });
    await sessao.login('aluno@example.com', 'senha');

    let cabecalhoRecebido: string | null = null;
    const fetchCru: typeof fetch = async (_input, init) => {
      const headers = (init?.headers ?? {}) as Record<string, string>;
      cabecalhoRecebido = headers.Authorization ?? null;
      return new Response(null, { status: 200 });
    };
    const comFetchCru = criarSessaoAutenticada({ cliente, armazenamento, fetchCru });
    await comFetchCru.login('aluno@example.com', 'senha');

    await comFetchCru.fetchAutenticado('http://api.local/x');

    expect(cabecalhoRecebido).toBe('Bearer access-1');
  });

  it(
    'duas chamadas concorrentes que recebem 401 disparam UM único refresh — ' +
      'o critério de aceite central do card',
    async () => {
      const armazenamento = armazenamentoFalso();
      let chamadasDeRenovacao = 0;
      const cliente = clienteFalso({
        async renovarTokens() {
          chamadasDeRenovacao += 1;
          // Um atraso deliberado: sem ele, o teste passaria mesmo se a
          // dedup estivesse quebrada, porque a segunda chamada só
          // aconteceria depois da primeira já ter terminado.
          await new Promise((resolve) => setTimeout(resolve, 5));
          return PAR_RENOVADO;
        },
      });
      const sessao = criarSessaoAutenticada({ cliente, armazenamento });
      await sessao.login('aluno@example.com', 'senha'); // accessToken = access-1

      const fetchCru: typeof fetch = async (_input, init) => {
        const headers = (init?.headers ?? {}) as Record<string, string>;
        return new Response(null, {
          status: headers.Authorization === 'Bearer access-2' ? 200 : 401,
        });
      };
      const comAccessVelho = criarSessaoAutenticada({
        cliente,
        armazenamento,
        fetchCru,
      });
      // Reaplica o login para que ESTA instância também comece com access-1
      // — duas instâncias porque cada uma tem seu próprio fechamento de
      // `accessToken`, e o que importa aqui é a dedup DENTRO de uma só.
      await comAccessVelho.login('aluno@example.com', 'senha');

      const [r1, r2] = await Promise.all([
        comAccessVelho.fetchAutenticado('http://api.local/x'),
        comAccessVelho.fetchAutenticado('http://api.local/y'),
      ]);

      expect(r1.status).toBe(200);
      expect(r2.status).toBe(200);
      expect(chamadasDeRenovacao).toBe(1);
    },
  );

  it('resposta que não é 401 nunca chama renovarTokens', async () => {
    const armazenamento = armazenamentoFalso();
    const cliente = clienteFalso();
    const fetchCru: typeof fetch = async () => new Response(null, { status: 200 });
    const sessao = criarSessaoAutenticada({ cliente, armazenamento, fetchCru });
    await sessao.login('aluno@example.com', 'senha');

    await sessao.fetchAutenticado('http://api.local/x');

    expect(cliente.chamadas.renovarTokens).toBeUndefined();
  });

  it('401 mesmo depois de renovar (credencial de fato inválida) não entra em loop', async () => {
    const armazenamento = armazenamentoFalso();
    const cliente = clienteFalso();
    let chamadasDeFetch = 0;
    const fetchCru: typeof fetch = async () => {
      chamadasDeFetch += 1;
      return new Response(null, { status: 401 });
    };
    const sessao = criarSessaoAutenticada({ cliente, armazenamento, fetchCru });
    await sessao.login('aluno@example.com', 'senha');

    const resposta = await sessao.fetchAutenticado('http://api.local/x');

    expect(resposta.status).toBe(401);
    // Uma tentativa original + uma retentativa pós-refresh. Nunca mais.
    expect(chamadasDeFetch).toBe(2);
    expect(cliente.chamadas.renovarTokens).toBe(1);
  });
});

describe('estados observados via aoMudarEstado', () => {
  it('emite carregando implícito só até a primeira decisão, depois autenticado/não', async () => {
    const armazenamento = armazenamentoFalso();
    const cliente = clienteFalso();
    const estados: EstadoDaSessao[] = [];
    const sessao = criarSessaoAutenticada({
      cliente,
      armazenamento,
      aoMudarEstado: (estado) => estados.push(estado),
    });

    await sessao.login('aluno@example.com', 'senha');
    await sessao.sair();

    expect(estados).toEqual(['autenticado', 'nao_autenticado']);
  });
});
