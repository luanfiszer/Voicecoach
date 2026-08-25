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
};

/** Erro de resposta da API, com o que o Problem Details (ADR-0040) trouxer. */
export class ErroDaApi extends Error {
  readonly status: number;
  readonly detalhe: string | null;

  constructor(status: number, titulo: string, detalhe: string | null) {
    super(titulo);
    this.name = 'ErroDaApi';
    this.status = status;
    this.detalhe = detalhe;
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
  return true; // falha de rede: é o caso de uso inteiro da idempotência
}

export function criarCliente(opcoes: OpcoesDoCliente): Cliente {
  const base = opcoes.baseUrl.replace(/\/+$/, '');
  const executar = opcoes.fetch ?? fetch;

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
    try {
      const corpo = (await resposta.json()) as { title?: string; detail?: string };
      if (corpo.title) titulo = corpo.title;
      if (corpo.detail) detalhe = corpo.detail;
    } catch {
      detalhe = null;
    }
    throw new ErroDaApi(resposta.status, titulo, detalhe);
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
