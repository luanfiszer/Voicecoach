/**
 * O client HTTP do Voicecoach — a fronteira entre os apps e o backend.
 *
 * **Regra deste pacote:** ele conhece HTTP e o contrato, e nada de produto
 * (`packages/api-client/README.md`). Não há estado de tela, fila de playback nem
 * regra pedagógica aqui — quem toca áudio é o app, que é quem conhece o aparelho.
 *
 * **Forma: função-fábrica, não classe.** `criarCliente({ baseUrl, fetch })`
 * devolve um objeto de funções. O motivo é testabilidade: o `fetch` entra por
 * parâmetro, então um dublê é um objeto literal — sem framework de mock, sem
 * `jest.mock`, e o `tsc --strict` reprova o dublê que não satisfaz o tipo. É o
 * mesmo mecanismo que o `Protocol` dá no backend, do outro lado do monorepo.
 *
 * **A `Idempotency-Key` é PARÂMETRO, nunca gerada aqui dentro.** Gerá-la dentro
 * de `enviarTurn` daria uma chave por tentativa — que é exatamente o turn
 * duplicado que o ADR-0042 existe para impedir. Ela nasce quando a gravação
 * termina, e o retry reusa a mesma.
 */

import { ErroDeStream, type EventoDoTurn, lerEventos } from './eventos';
import type { components } from './schema';

type Schemas = components['schemas'];

export type Sessao = Schemas['SessionResponse'];
export type Turn = Schemas['TurnResponse'];
export type TurnAceito = Schemas['TurnAcceptedResponse'];
export type Trecho = Schemas['ChunkPayload'];
export type SessaoDoHistorico = Schemas['SessionListEntry'];
export type ListaDeSessoes = Schemas['SessionListResponse'];
/** `reply` é a resposta do professor; `correction` é a explicação de uma correção. */
export type AlvoDeTraducao = Schemas['TranslationTarget'];
export type Traducao = Schemas['TranslationResponse'];
/** O par emitido por login e por refresh — mesma forma nos dois (ADR-0007). */
export type ParDeTokens = Schemas['TokenPairResponse'];

export type OpcoesDoCliente = {
  baseUrl: string;
  /** Injetável para teste; default é o `fetch` global. */
  fetch?: typeof fetch;
  /**
   * O token de sessão. Vazio nesta fase — a auth real é o ADR-0007, e o lugar
   * dela já existe para que ligá-la seja uma linha, não uma refatoração.
   */
  token?: string | null;
};

export type EnvioDeTurn = {
  sessionId: string;
  /**
   * Os bytes da fala. **`Blob`, e só `Blob`** — não a URI do arquivo.
   *
   * O idioma que todo tutorial de React Native ensina é
   * `formData.append('audio', { uri, name, type })`. **Ele não funciona aqui**, e
   * isso foi medido no Expo Go SDK 57, no Simulador, contra o endpoint real:
   *
   * ```
   * uri+name+type -> ERRO Unsupported FormDataPart implementation
   * uri só        -> ERRO Unsupported FormDataPart implementation
   * blob          -> HTTP 202
   * ```
   *
   * Aceitar a URI aqui seria oferecer um caminho que falha em runtime com uma
   * mensagem que não explica nada. Quem tem uma URI a converte antes — no app é
   * `src/features/turno/arquivoLocal.ts`, que é onde o conhecimento sobre o
   * sistema de arquivos do aparelho deve morar (este pacote não conhece produto
   * nem plataforma).
   */
  audio: Blob;
  /** Nome da parte do multipart. A extensão é o que o servidor lê. */
  nomeDoArquivo?: string;
  /** Gerada UMA vez, ao concluir a gravação. O retry reusa esta mesma. */
  idempotencyKey: string;
  /** Tentativas totais, incluindo a primeira. */
  tentativas?: number;
  sinal?: AbortSignal;
};

export type AcompanhamentoDoTurn = {
  sinal?: AbortSignal;
  /**
   * O `id:` do último evento recebido (ADR-0041).
   *
   * **Id fora do esquema é 400, não "comece do começo"** — então não invente um:
   * mande o último que você recebeu, ou nenhum.
   */
  ultimoEventoId?: string | null;
};

export type Cliente = {
  criarSessao(sinal?: AbortSignal): Promise<Sessao>;
  enviarTurn(envio: EnvioDeTurn): Promise<TurnAceito>;
  obterTurn(turnId: string, sinal?: AbortSignal): Promise<Turn>;
  acompanharTurn(
    turnId: string,
    opcoes?: AcompanhamentoDoTurn,
  ): AsyncGenerator<EventoDoTurn>;
  /**
   * O histórico do aluno (CARD-030), mais recente primeiro.
   *
   * `dias` é a janela do contrato — sem ela, o servidor usa o default de 30
   * (a promessa da tela: "sessões anteriores a 30 dias vivem no app web").
   */
  listarSessoes(dias?: number, sinal?: AbortSignal): Promise<ListaDeSessoes>;
  /**
   * "Descartar" (CARD-032): o turn some da tela ativa, sem apagar nada no
   * servidor. Idempotente — chamar duas vezes é `204` as duas.
   */
  descartarTurn(turnId: string, sinal?: AbortSignal): Promise<void>;
  /**
   * O botão `traduzir` (CARD-058, endpoint do CARD-036). **O corpo diz QUAL
   * texto, nunca o texto** — o cliente escolhe entre alvos fechados
   * (`AlvoDeTraducao`), nunca manda texto livre (RF1 do CARD-036: um endpoint
   * de texto livre seria proxy de LLM aberto pago por nós). Pedir a mesma
   * tradução duas vezes não cobra duas — o servidor responde `cached: true`
   * (RF4), então este método não precisa de lógica de cache própria.
   */
  traduzirTexto(
    turnId: string,
    alvo: AlvoDeTraducao,
    index?: number,
    sinal?: AbortSignal,
  ): Promise<Traducao>;
  /**
   * Cadastro por e-mail+senha (CARD-050, ADR-0007).
   *
   * **A resposta é sempre a mesma**, e-mail novo ou já cadastrado — não vazar
   * quais e-mails existem é requisito do servidor (CARD-049), não deste
   * client. O aluno vê "confirme seu e-mail" nos dois casos.
   */
  registrar(email: string, password: string, sinal?: AbortSignal): Promise<void>;
  /** Devolve o par de tokens. Quem guarda em `expo-secure-store` é o app. */
  login(email: string, password: string, sinal?: AbortSignal): Promise<ParDeTokens>;
  /**
   * Rotaciona o par de tokens (ADR-0007).
   *
   * **Nunca chame isto de dentro de um retry automático.** Repetir um
   * refresh com o MESMO token é exatamente o gesto que o servidor lê como
   * reuso e revoga a família inteira (CARD-049, item 3) — cada chamada
   * daqui tem de corresponder a uma decisão deliberada de renovar, nunca a
   * uma tentativa de rede que se repete sozinha.
   */
  renovarTokens(refreshToken: string, sinal?: AbortSignal): Promise<ParDeTokens>;
  /** Revoga a família do refresh apresentado. Idempotente do lado do servidor. */
  sair(refreshToken: string, sinal?: AbortSignal): Promise<void>;
  /** `GET` porque é o link que o aluno clica no e-mail. */
  confirmarEmail(token: string, sinal?: AbortSignal): Promise<void>;
  reenviarConfirmacao(email: string, sinal?: AbortSignal): Promise<void>;
  pedirRedefinicaoDeSenha(email: string, sinal?: AbortSignal): Promise<void>;
  /** Troca a senha e desloga TODAS as sessões do aluno (ADR-0007) — não só esta. */
  redefinirSenha(token: string, novaSenha: string, sinal?: AbortSignal): Promise<void>;
  /**
   * Exclui a própria conta (CARD-051, ADR-0069) — LGPD e Guideline 5.1.1(v).
   *
   * **Só marca e revoga, do lado do servidor; não apaga nada aqui.** É por
   * isso que este método não devolve nada além de `void`: não há "o que
   * restou" para o cliente ler, e é o próprio 204 que confirma "não
   * consegue mais entrar, a partir de agora" — o critério de aceite do
   * card. O `fetch` injetado é quem carrega o `Authorization`; este método
   * não recebe token.
   */
  excluirConta(sinal?: AbortSignal): Promise<void>;
};

/**
 * Erro de **resposta** da API, com o que o Problem Details (ADR-0040) trouxer.
 *
 * Tem `status`: o servidor respondeu, e o que ele disse é para o aluno ler.
 * Contraste com `ErroDeRede`, logo abaixo.
 *
 * **`tipo` é a URN, e é ela — não `status` nem `titulo` — que o CARD-027 usa
 * para discriminar telas.** `status` sozinho não distingue cota de kill
 * switch (os dois são desfechos de negócio, `429`/`503`); `titulo`/`detalhe`
 * são para o aluno ler, não para o código comparar (ADR-0040: "o `type` é a
 * chave semântica, não o texto"). Antes deste card, `tipo` não existia aqui —
 * o corpo do Problem Details era lido só até `title`/`detail`, e o chamador
 * não tinha como saber SE ERA cota, kill switch, ou "algo deu errado".
 */
export class ErroDaApi extends Error {
  readonly status: number;
  readonly detalhe: string | null;
  readonly tipo: string | null;

  constructor(
    status: number,
    titulo: string,
    detalhe: string | null,
    tipo: string | null,
  ) {
    super(titulo);
    this.name = 'ErroDaApi';
    this.status = status;
    this.detalhe = detalhe;
    this.tipo = tipo;
  }
}

/**
 * Falha de **transporte**: a requisição não chegou a ter resposta.
 *
 * **Não tem `status`** — e essa é a diferença que importa. Medido:
 *
 * ```
 * fetch("http://127.0.0.1:59999/…")
 *   TypeError: fetch failed        (no React Native: "Network request failed")
 *   status  -> (não existe)
 *   message -> não contém o host
 * ```
 *
 * No Node o host ainda aparece em `cause.code`/`cause.message` (`ECONNREFUSED`);
 * no Hermes não há `cause` nenhuma, e sobra um texto fixo. O único lugar que
 * **sabe** qual endereço falhou é este client, porque foi ele quem montou a URL
 * — por isso a tradução mora aqui e não na tela (ADR-0054 item 7).
 *
 * Quem vê esta mensagem é o desenvolvedor com um aparelho na mão: Mac dormindo,
 * IP trocado pelo DHCP, backend não subiu, permissão de rede local negada. Copy
 * de aluno é assunto do `ErroDaApi`, que tem status e `title`.
 */
export class ErroDeRede extends Error {
  /** A base URL que o client tentou alcançar. */
  readonly host: string;
  /** O erro original, preservado para o log. */
  readonly causa: unknown;

  constructor(host: string, causa: unknown) {
    const detalhe = causa instanceof Error ? causa.message : String(causa);
    super(`não foi possível alcançar ${host} (${detalhe})`);
    this.name = 'ErroDeRede';
    this.host = host;
    this.causa = causa;
  }
}

export type { EventoDoTurn };
export { ErroDeStream };

/** Passos do backoff, em ms. O comprimento define o teto de tentativas. */
const BACKOFF = [400, 1200, 3000];

const TENTATIVAS_PADRAO = 3;

function esperar(ms: number, sinal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    sinal?.addEventListener(
      'abort',
      () => {
        clearTimeout(timer);
        reject(new DOMException('abortado', 'AbortError'));
      },
      { once: true },
    );
  });
}

/**
 * `5xx` e falha de rede se repetem; `4xx` não.
 *
 * Repetir um `4xx` é insistir num pedido que o servidor já disse ser inválido —
 * gasta bateria e atrasa a mensagem de erro que o aluno precisa ver.
 */
function valeRepetir(erro: unknown): boolean {
  if (erro instanceof ErroDaApi) return erro.status >= 500;
  if (erro instanceof DOMException && erro.name === 'AbortError') return false;
  return true; // ErroDeRede e afins: é o caso de uso inteiro da idempotência
}

export function criarCliente(opcoes: OpcoesDoCliente): Cliente {
  const base = opcoes.baseUrl.replace(/\/+$/, '');
  const fetchCru = opcoes.fetch ?? fetch;

  /**
   * Todo `fetch` do client passa por aqui, e só por isto: falha de transporte
   * vira `ErroDeRede` **nomeando o host**.
   *
   * O `AbortError` escapa intocado de propósito — ele não é falha de rede, é
   * cancelamento nosso, e `valeRepetir` conta com o tipo original para não
   * repetir o que o app acabou de cancelar.
   */
  async function executar(url: string, init: RequestInit): Promise<Response> {
    try {
      return await fetchCru(url, init);
    } catch (erro) {
      if (erro instanceof DOMException && erro.name === 'AbortError') throw erro;
      throw new ErroDeRede(base, erro);
    }
  }

  function cabecalhos(extras?: Record<string, string>): Record<string, string> {
    const saida: Record<string, string> = { ...extras };
    if (opcoes.token) saida.Authorization = `Bearer ${opcoes.token}`;
    return saida;
  }

  async function falhar(resposta: Response): Promise<never> {
    // Problem Details (RFC 9457 / ADR-0040). O corpo é lido com tolerância
    // porque um 502 de proxy não é JSON nenhum — e o app precisa de uma
    // mensagem, não de um `SyntaxError` por cima do erro original.
    let titulo = `HTTP ${resposta.status}`;
    let detalhe: string | null = null;
    let tipo: string | null = null;
    try {
      const corpo = (await resposta.json()) as {
        title?: string;
        detail?: string;
        type?: string;
      };
      if (corpo.title) titulo = corpo.title;
      if (corpo.detail) detalhe = corpo.detail;
      if (corpo.type) tipo = corpo.type;
    } catch {
      detalhe = null;
    }
    throw new ErroDaApi(resposta.status, titulo, detalhe, tipo);
  }

  async function json<T>(resposta: Response): Promise<T> {
    if (!resposta.ok) await falhar(resposta);
    return (await resposta.json()) as T;
  }

  return {
    async criarSessao(sinal?: AbortSignal): Promise<Sessao> {
      const resposta = await executar(`${base}/v1/sessions`, {
        method: 'POST',
        headers: cabecalhos(),
        signal: sinal ?? null,
      });
      return json<Sessao>(resposta);
    },

    async enviarTurn(envio: EnvioDeTurn): Promise<TurnAceito> {
      const total = envio.tentativas ?? TENTATIVAS_PADRAO;
      let ultimoErro: unknown = null;

      for (let tentativa = 0; tentativa < total; tentativa++) {
        if (tentativa > 0) {
          await esperar(
            BACKOFF[Math.min(tentativa - 1, BACKOFF.length - 1)] ?? 3000,
            envio.sinal,
          );
        }
        try {
          // **O corpo é montado a cada tentativa, a chave não.** Um `FormData`
          // já consumido não pode ser reenviado; a `Idempotency-Key` é o que
          // garante que reenviar não cria turn novo (ADR-0042).
          const corpo = new FormData();
          corpo.append('audio', envio.audio, envio.nomeDoArquivo ?? 'fala.m4a');

          const resposta = await executar(
            `${base}/v1/sessions/${envio.sessionId}/turns`,
            {
              method: 'POST',
              headers: cabecalhos({ 'Idempotency-Key': envio.idempotencyKey }),
              body: corpo,
              signal: envio.sinal ?? null,
            },
          );
          return await json<TurnAceito>(resposta);
        } catch (erro) {
          ultimoErro = erro;
          if (!valeRepetir(erro)) throw erro;
        }
      }
      throw ultimoErro;
    },

    async obterTurn(turnId: string, sinal?: AbortSignal): Promise<Turn> {
      const resposta = await executar(`${base}/v1/turns/${turnId}`, {
        headers: cabecalhos(),
        signal: sinal ?? null,
      });
      return json<Turn>(resposta);
    },

    async listarSessoes(dias?: number, sinal?: AbortSignal): Promise<ListaDeSessoes> {
      const query = dias !== undefined ? `?days=${dias}` : '';
      const resposta = await executar(`${base}/v1/sessions${query}`, {
        headers: cabecalhos(),
        signal: sinal ?? null,
      });
      return json<ListaDeSessoes>(resposta);
    },

    async descartarTurn(turnId: string, sinal?: AbortSignal): Promise<void> {
      const resposta = await executar(`${base}/v1/turns/${turnId}/discard`, {
        method: 'POST',
        headers: cabecalhos(),
        signal: sinal ?? null,
      });
      // `204 No Content`: nenhum corpo a ler. `!resposta.ok` cobre o 404/409
      // que o CARD-032 define (turn de outro aluno ou já concluído).
      if (!resposta.ok) await falhar(resposta);
    },

    async traduzirTexto(
      turnId: string,
      alvo: AlvoDeTraducao,
      index?: number,
      sinal?: AbortSignal,
    ): Promise<Traducao> {
      const resposta = await executar(`${base}/v1/turns/${turnId}/translations`, {
        method: 'POST',
        headers: cabecalhos({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ target: alvo, index: index ?? 0 }),
        signal: sinal ?? null,
      });
      return json<Traducao>(resposta);
    },

    async registrar(
      email: string,
      password: string,
      sinal?: AbortSignal,
    ): Promise<void> {
      const resposta = await executar(`${base}/v1/auth/register`, {
        method: 'POST',
        headers: cabecalhos({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ email, password }),
        signal: sinal ?? null,
      });
      if (!resposta.ok) await falhar(resposta);
    },

    async login(
      email: string,
      password: string,
      sinal?: AbortSignal,
    ): Promise<ParDeTokens> {
      const resposta = await executar(`${base}/v1/auth/login`, {
        method: 'POST',
        headers: cabecalhos({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ email, password }),
        signal: sinal ?? null,
      });
      return json<ParDeTokens>(resposta);
    },

    async renovarTokens(
      refreshToken: string,
      sinal?: AbortSignal,
    ): Promise<ParDeTokens> {
      const resposta = await executar(`${base}/v1/auth/refresh`, {
        method: 'POST',
        headers: cabecalhos({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ refresh_token: refreshToken }),
        signal: sinal ?? null,
      });
      return json<ParDeTokens>(resposta);
    },

    async sair(refreshToken: string, sinal?: AbortSignal): Promise<void> {
      const resposta = await executar(`${base}/v1/auth/logout`, {
        method: 'POST',
        headers: cabecalhos({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ refresh_token: refreshToken }),
        signal: sinal ?? null,
      });
      // `204 No Content` no caminho comum; qualquer outro status é erro.
      if (!resposta.ok) await falhar(resposta);
    },

    async confirmarEmail(token: string, sinal?: AbortSignal): Promise<void> {
      const resposta = await executar(
        `${base}/v1/auth/confirm-email?token=${encodeURIComponent(token)}`,
        { headers: cabecalhos(), signal: sinal ?? null },
      );
      if (!resposta.ok) await falhar(resposta);
    },

    async reenviarConfirmacao(email: string, sinal?: AbortSignal): Promise<void> {
      const resposta = await executar(`${base}/v1/auth/resend-confirmation`, {
        method: 'POST',
        headers: cabecalhos({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ email }),
        signal: sinal ?? null,
      });
      if (!resposta.ok) await falhar(resposta);
    },

    async pedirRedefinicaoDeSenha(email: string, sinal?: AbortSignal): Promise<void> {
      const resposta = await executar(`${base}/v1/auth/request-password-reset`, {
        method: 'POST',
        headers: cabecalhos({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ email }),
        signal: sinal ?? null,
      });
      if (!resposta.ok) await falhar(resposta);
    },

    async redefinirSenha(
      token: string,
      novaSenha: string,
      sinal?: AbortSignal,
    ): Promise<void> {
      const resposta = await executar(`${base}/v1/auth/reset-password`, {
        method: 'POST',
        headers: cabecalhos({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ token, new_password: novaSenha }),
        signal: sinal ?? null,
      });
      if (!resposta.ok) await falhar(resposta);
    },

    async excluirConta(sinal?: AbortSignal): Promise<void> {
      const resposta = await executar(`${base}/v1/students/me`, {
        method: 'DELETE',
        headers: cabecalhos(),
        signal: sinal ?? null,
      });
      if (!resposta.ok) await falhar(resposta);
    },

    async *acompanharTurn(
      turnId: string,
      opcoes: AcompanhamentoDoTurn = {},
    ): AsyncGenerator<EventoDoTurn> {
      const extras: Record<string, string> = { Accept: 'text/event-stream' };
      if (opcoes.ultimoEventoId) extras['Last-Event-ID'] = opcoes.ultimoEventoId;

      const resposta = await executar(`${base}/v1/turns/${turnId}/events`, {
        headers: cabecalhos(extras),
        signal: opcoes.sinal ?? null,
      });
      if (!resposta.ok) await falhar(resposta);

      yield* lerEventos(resposta, opcoes.sinal);
    },
  };
}
