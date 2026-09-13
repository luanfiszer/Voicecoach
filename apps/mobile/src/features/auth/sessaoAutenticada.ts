/**
 * A sessão autenticada — a máquina de estados que o CARD-050 pede (ADR-0007).
 *
 * **Nenhum import nativo, nenhum import de React.** É esta separação que torna
 * o pedaço mais caro de errar do card — a corrida do refresh concorrente —
 * testável em Node puro, sem mock de `expo-secure-store` (ADR-0061). Quem liga
 * isto ao aparelho é `armazenamentoDeToken.ts`; quem liga isto à árvore de
 * componentes é `useSessao.tsx`.
 *
 * **A corrida que existe mesmo sem paralelismo.** JavaScript tem um event loop
 * só — não há duas threads disputando a mesma variável. A corrida aqui é
 * temporal: entre o `await` que confirma "o access expirou" e o `await` que
 * termina o refresh, uma SEGUNDA chamada pode entrar e decidir a mesma coisa,
 * porque nada a impede de rodar nessa janela. Sem uma promessa compartilhada,
 * as duas chamariam `renovarTokens` com o MESMO refresh token — e a segunda
 * seria lida pelo servidor como reuso, revogando a família inteira (CARD-049,
 * item 3). A defesa não é um lock (não existe primitiva de lock em JS de
 * propósito): é guardar a PROMESSA em vez do resultado, e todo chamador que
 * chegar enquanto ela ainda não resolveu recebe a mesma promessa, não inicia
 * uma nova.
 */

import type { Cliente, ParDeTokens } from '@voicecoach/api-client';

export type ArmazenamentoDeSessao = {
  obterRefreshToken(): Promise<string | null>;
  definirRefreshToken(token: string): Promise<void>;
  limparRefreshToken(): Promise<void>;
};

export type EstadoDaSessao = 'carregando' | 'autenticado' | 'nao_autenticado';

/** As chamadas do client que esta máquina consome — um subconjunto de `Cliente`. */
export type ClienteDeAuth = Pick<
  Cliente,
  | 'login'
  | 'registrar'
  | 'renovarTokens'
  | 'sair'
  | 'confirmarEmail'
  | 'reenviarConfirmacao'
  | 'pedirRedefinicaoDeSenha'
  | 'redefinirSenha'
>;

export type SessaoAutenticada = {
  obterEstado(): EstadoDaSessao;
  /** Chamado uma vez, ao montar o app: tenta o login silencioso. */
  inicializar(): Promise<void>;
  login(email: string, senha: string): Promise<void>;
  registrar(email: string, senha: string): Promise<void>;
  sair(): Promise<void>;
  confirmarEmail(token: string): Promise<void>;
  reenviarConfirmacao(email: string): Promise<void>;
  pedirRedefinicaoDeSenha(email: string): Promise<void>;
  redefinirSenha(token: string, novaSenha: string): Promise<void>;
  /**
   * Substituto de `fetch` que injeta o `Authorization` e, num `401`, renova
   * e repete a chamada original **uma vez** — nunca em loop, porque um `401`
   * depois de um refresh recém-feito é a credencial mesmo inválida, não uma
   * corrida a mais para resolver.
   */
  fetchAutenticado(input: RequestInfo | URL, init?: RequestInit): Promise<Response>;
};

export function criarSessaoAutenticada(opcoes: {
  cliente: ClienteDeAuth;
  armazenamento: ArmazenamentoDeSessao;
  /** Injetável em teste; default é o `fetch` global. */
  fetchCru?: typeof fetch;
  aoMudarEstado?: (estado: EstadoDaSessao) => void;
}): SessaoAutenticada {
  const fetchCru = opcoes.fetchCru ?? fetch;

  let estado: EstadoDaSessao = 'carregando';
  let accessToken: string | null = null;
  // A peça central do card: a promessa em voo, compartilhada por quem quer
  // que chegue enquanto ela ainda não terminou.
  let promessaDeRenovacao: Promise<string | null> | null = null;

  function definirEstado(novo: EstadoDaSessao): void {
    estado = novo;
    opcoes.aoMudarEstado?.(novo);
  }

  function aplicarParDeTokens(par: ParDeTokens): Promise<void> {
    accessToken = par.access_token;
    definirEstado('autenticado');
    return opcoes.armazenamento.definirRefreshToken(par.refresh_token);
  }

  async function limparSessao(): Promise<void> {
    accessToken = null;
    definirEstado('nao_autenticado');
    await opcoes.armazenamento.limparRefreshToken();
  }

  /**
   * Renova, ou devolve a renovação que já está em voo.
   *
   * **Por que `promessaDeRenovacao` é limpa no `finally` e não logo depois do
   * `await`.** Duas chamadas que cheguem antes da resolução top do MESMO tick
   * de microtask viam o mesmo valor de qualquer forma; o que o `finally`
   * garante é que a PRÓXIMA rodada (um novo 401, minutos depois) comece uma
   * renovação nova, e não reuse para sempre a promessa já resolvida.
   */
  async function renovar(): Promise<string | null> {
    if (promessaDeRenovacao) return promessaDeRenovacao;

    promessaDeRenovacao = (async () => {
      const refreshToken = await opcoes.armazenamento.obterRefreshToken();
      if (refreshToken === null) {
        await limparSessao();
        return null;
      }
      try {
        const par = await opcoes.cliente.renovarTokens(refreshToken);
        await aplicarParDeTokens(par);
        return par.access_token;
      } catch {
        // Refresh inválido (expirado, reuso detectado, ou já revogado por
        // logout em outro aparelho): estado limpo, nada do aluno anterior
        // sobra na tela (critério de aceite do card).
        await limparSessao();
        return null;
      }
    })();

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
    const par = await opcoes.cliente.login(email, senha);
    await aplicarParDeTokens(par);
  }

  async function registrar(email: string, senha: string): Promise<void> {
    await opcoes.cliente.registrar(email, senha);
  }

  async function sair(): Promise<void> {
    const refreshToken = await opcoes.armazenamento.obterRefreshToken();
    await limparSessao();
    if (refreshToken !== null) {
      try {
        await opcoes.cliente.sair(refreshToken);
      } catch {
        // Mesmo padrão do "Descartar" do CARD-032: o objetivo é destravar a
        // tela na hora, não esperar confirmação do servidor para deixar.
      }
    }
  }

  async function confirmarEmail(token: string): Promise<void> {
    await opcoes.cliente.confirmarEmail(token);
  }

  async function reenviarConfirmacao(email: string): Promise<void> {
    await opcoes.cliente.reenviarConfirmacao(email);
  }

  async function pedirRedefinicaoDeSenha(email: string): Promise<void> {
    await opcoes.cliente.pedirRedefinicaoDeSenha(email);
  }

  async function redefinirSenha(token: string, novaSenha: string): Promise<void> {
    await opcoes.cliente.redefinirSenha(token, novaSenha);
  }

  function comAutorizacao(init: RequestInit, token: string | null): RequestInit {
    if (token === null) return init;
    return { ...init, headers: { ...init.headers, Authorization: `Bearer ${token}` } };
  }

  async function fetchAutenticado(
    input: RequestInfo | URL,
    init: RequestInit = {},
  ): Promise<Response> {
    // Sem token ainda (chamada antes de `inicializar()` terminar, ou sessão
    // que nunca logou): tenta renovar uma vez antes da primeira tentativa —
    // é o que faz um refresh válido guardado do boot anterior "simplesmente
    // funcionar" sem que o chamador saiba que havia uma renovação pendente.
    if (accessToken === null) await renovar();

    const resposta = await fetchCru(input, comAutorizacao(init, accessToken));
    if (resposta.status !== 401) return resposta;

    // O relógio do aparelho não manda (critério de aceite do card) — só o
    // 401 decide que é hora de renovar, esteja o relógio certo ou não.
    const tokenNovo = await renovar();
    return fetchCru(input, comAutorizacao(init, tokenNovo));
  }

  return {
    obterEstado: () => estado,
    inicializar,
    login,
    registrar,
    sair,
    confirmarEmail,
    reenviarConfirmacao,
    pedirRedefinicaoDeSenha,
    redefinirSenha,
    fetchAutenticado,
  };
}
