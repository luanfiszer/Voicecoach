/**
 * A sessão autenticada da web (CARD-064, ADR-0077) — irmã de
 * `apps/mobile/src/features/auth/sessaoAutenticada.ts`, com duas diferenças
 * que são o card inteiro:
 *
 * 1. **Não há refresh token aqui.** Ele mora num cookie `HttpOnly` que o
 *    servidor grava e o navegador manda sozinho para `/v1/auth/web/*`. Este
 *    módulo nunca o vê — só o access token de 15 min, guardado numa variável
 *    (memória da aba). Recarregar a página perde o access e o recupera com um
 *    refresh silencioso no `inicializar`.
 *
 * 2. **Abas são clientes concorrentes do mesmo cookie.** O mobile só precisa
 *    impedir que duas chamadas DO MESMO app renovem juntas (a promessa
 *    compartilhada). Na web, duas abas são dois "apps" com o mesmo cookie — e
 *    duas renovações simultâneas são lidas pelo servidor como reuso, revogando
 *    a família e deslogando as duas (demonstrado com `curl` no CARD-064). A
 *    renovação roda dentro de uma `Trava` entre abas (Web Locks API): a
 *    segunda aba espera e, quando entra, o navegador já lhe entrega o cookie
 *    rotacionado pela primeira.
 *
 * Sem React, sem `window`, sem `navigator`: tudo de plataforma entra por
 * parâmetro, e é isso que deixa o teste das duas abas rodar em Node.
 */

import type { Cliente, TokenDeAcesso } from '@voicecoach/api-client';

export type EstadoDaSessao = 'carregando' | 'autenticado' | 'nao_autenticado';

/** As chamadas do client que esta máquina consome. */
export type ClienteDeAuthWeb = Pick<
  Cliente,
  | 'loginWeb'
  | 'loginGoogleWeb'
  | 'renovarSessaoWeb'
  | 'sairDaWeb'
  | 'registrar'
  | 'confirmarEmail'
  | 'reenviarConfirmacao'
  | 'pedirRedefinicaoDeSenha'
  | 'redefinirSenha'
>;

/**
 * Exclusão mútua ENTRE ABAS: roda `fn` só quando nenhuma outra aba estiver
 * dentro de uma trava com o mesmo nome.
 */
export type Trava = <T>(nome: string, fn: () => Promise<T>) => Promise<T>;

/** O nome da trava — o mesmo em todas as abas, ou ela não trava nada. */
export const TRAVA_DE_RENOVACAO = 'voicecoach-renovacao-de-sessao';

/**
 * A trava do navegador: `navigator.locks` (Web Locks API).
 *
 * **Sem a API, cai para "sem trava"** — e isso é escolha, não descuido: a
 * alternativa seria recusar o navegador inteiro. O preço do recuo é o
 * comportamento de antes (duas abas renovando juntas podem deslogar), que é
 * desconfortável mas não inseguro.
 */
export function travaDoNavegador(locks: LockManager | undefined): Trava {
  if (!locks) return (_nome, fn) => fn();
  return (nome, fn) => locks.request(nome, fn);
}

export type SessaoWeb = {
  obterEstado(): EstadoDaSessao;
  /** Chamado uma vez, ao montar o app: tenta o refresh silencioso pelo cookie. */
  inicializar(): Promise<void>;
  login(email: string, senha: string): Promise<void>;
  loginGoogle(idToken: string): Promise<void>;
  registrar(email: string, senha: string): Promise<void>;
  sair(): Promise<void>;
  confirmarEmail(token: string): Promise<void>;
  reenviarConfirmacao(email: string): Promise<void>;
  pedirRedefinicaoDeSenha(email: string): Promise<void>;
  redefinirSenha(token: string, novaSenha: string): Promise<void>;
  /**
   * `fetch` com `Authorization`; num `401`, renova e repete **uma vez** —
   * mesmo contrato do mobile.
   */
  fetchAutenticado(input: RequestInfo | URL, init?: RequestInit): Promise<Response>;
};

export function criarSessaoWeb(opcoes: {
  cliente: ClienteDeAuthWeb;
  trava: Trava;
  fetchCru?: typeof fetch;
  aoMudarEstado?: (estado: EstadoDaSessao) => void;
}): SessaoWeb {
  const fetchCru = opcoes.fetchCru ?? fetch;

  let estado: EstadoDaSessao = 'carregando';
  let accessToken: string | null = null;
  // Dentro da MESMA aba, a mesma defesa do mobile: quem chega enquanto uma
  // renovação está em voo recebe a mesma promessa, não começa outra.
  let promessaDeRenovacao: Promise<string | null> | null = null;

  function definirEstado(novo: EstadoDaSessao): void {
    estado = novo;
    opcoes.aoMudarEstado?.(novo);
  }

  function aplicar(acesso: TokenDeAcesso): void {
    accessToken = acesso.access_token;
    definirEstado('autenticado');
  }

  function limpar(): void {
    accessToken = null;
    definirEstado('nao_autenticado');
  }

  async function renovar(): Promise<string | null> {
    if (promessaDeRenovacao) return promessaDeRenovacao;

    promessaDeRenovacao = opcoes.trava(TRAVA_DE_RENOVACAO, async () => {
      try {
        const acesso = await opcoes.cliente.renovarSessaoWeb();
        aplicar(acesso);
        return acesso.access_token;
      } catch {
        // Sem cookie, cookie expirado, ou família revogada: tela de login.
        limpar();
        return null;
      }
    });

    try {
      return await promessaDeRenovacao;
    } finally {
      promessaDeRenovacao = null;
    }
  }

  async function inicializar(): Promise<void> {
    await renovar();
  }

  async function login(email: string, senha: string): Promise<void> {
    aplicar(await opcoes.cliente.loginWeb(email, senha));
  }

  async function loginGoogle(idToken: string): Promise<void> {
    aplicar(await opcoes.cliente.loginGoogleWeb(idToken));
  }

  async function sair(): Promise<void> {
    try {
      await opcoes.cliente.sairDaWeb();
    } catch {
      // Falhar em avisar o servidor não pode manter o aluno logado nesta aba.
    }
    limpar();
  }

  function comAutorizacao(init: RequestInit | undefined, token: string): RequestInit {
    const cabecalhos = new Headers(init?.headers);
    cabecalhos.set('Authorization', `Bearer ${token}`);
    return { ...init, headers: cabecalhos };
  }

  async function fetchAutenticado(
    input: RequestInfo | URL,
    init?: RequestInit,
  ): Promise<Response> {
    const token = accessToken ?? (await renovar());
    if (token === null) return fetchCru(input, init);

    const resposta = await fetchCru(input, comAutorizacao(init, token));
    if (resposta.status !== 401) return resposta;

    const renovado = await renovar();
    if (renovado === null) return resposta;
    return fetchCru(input, comAutorizacao(init, renovado));
  }

  return {
    obterEstado: () => estado,
    inicializar,
    login,
    loginGoogle,
    registrar: (email, senha) => opcoes.cliente.registrar(email, senha),
    sair,
    confirmarEmail: (token) => opcoes.cliente.confirmarEmail(token),
    reenviarConfirmacao: (email) => opcoes.cliente.reenviarConfirmacao(email),
    pedirRedefinicaoDeSenha: (email) => opcoes.cliente.pedirRedefinicaoDeSenha(email),
    redefinirSenha: (token, novaSenha) =>
      opcoes.cliente.redefinirSenha(token, novaSenha),
    fetchAutenticado,
  };
}
