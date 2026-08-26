/**
 * O transporte da entrega progressiva: `text/event-stream` lido de
 * `response.body`, sem polyfill e sem dev build (ADR-0044).
 *
 * **Por que não `EventSource` nem `react-native-sse`.** O `EventSource` nativo
 * não aceita `Authorization` (ADR-0026), o que mataria a auth do ADR-0007 antes
 * de ela nascer. O polyfill resolveria isso e traria reconexão automática de
 * brinde — mas o spike do CARD-011 mediu, dentro do Expo Go, contra o endpoint
 * real: o `fetch` global entrega o stream **em pedaços** (5 leituras,
 * `chunk 0` em 1,65 s). Dependência que não se justifica não entra (ADR-0044).
 *
 * **A armadilha que custa uma sessão inteira:** o `sse-starlette` termina cada
 * linha com **CRLF**, então o separador de eventos é `\r\n\r\n`. Procurar
 * `\n\n` faz o stream chegar e nenhum evento ser reconhecido — sem erro, sem
 * log, parecendo "SSE não funciona no Expo Go". Daí a normalização antes de
 * qualquer `split`.
 */

import type { components } from './schema';

type Schemas = components['schemas'];

/**
 * Os cinco eventos do ADR-0026, como união discriminada.
 *
 * Os payloads são **gerados** do OpenAPI (ADR-0008) — e passaram a existir lá no
 * CARD-012: quatro dos cinco ficavam de fora, porque a rota do stream não
 * devolve modelo pydantic. Ver `TurnEventPayloads` no backend.
 */
export type EventoDoTurn =
  | { id: string; tipo: 'transcribed'; dados: Schemas['TranscribedPayload'] }
  | { id: string; tipo: 'chunk'; dados: Schemas['ChunkPayload'] }
  | { id: string; tipo: 'feedback'; dados: Schemas['FeedbackPayload'] }
  | { id: string; tipo: 'completed'; dados: Schemas['CompletedPayload'] }
  | { id: string; tipo: 'failed'; dados: Schemas['FailedPayload'] };

/** Os nomes de evento que o servidor emite (`wire_name`, ADR-0035 item 6). */
const TIPOS = ['transcribed', 'chunk', 'feedback', 'completed', 'failed'] as const;

type TipoDeEvento = (typeof TIPOS)[number];

function ehTipoConhecido(nome: string): nome is TipoDeEvento {
  return (TIPOS as readonly string[]).includes(nome);
}

/** Um bloco cru do protocolo, antes de saber o que ele significa. */
type Bloco = { id: string | null; evento: string; dados: string };

/**
 * Separa um buffer já normalizado em blocos de evento.
 *
 * `function*` é um **generator**: uma função que devolve valores aos poucos, sem
 * montar a lista inteira na memória, e que pode ser consumida com `for...of`.
 * Aqui ele existe porque um pedaço do stream pode conter vários eventos.
 */
function* blocos(buffer: string): Generator<Bloco> {
  for (const bruto of buffer.split('\n\n')) {
    if (!bruto.trim()) continue;

    let id: string | null = null;
    let evento = 'message';
    const dados: string[] = [];

    for (const linha of bruto.split('\n')) {
      if (linha.startsWith(':')) continue; // comentário / keep-alive
      if (linha.startsWith('id:')) id = linha.slice(3).trim();
      else if (linha.startsWith('event:')) evento = linha.slice(6).trim();
      else if (linha.startsWith('data:')) dados.push(linha.slice(5).trim());
    }

    yield { id, evento, dados: dados.join('\n') };
  }
}

/**
 * Traduz um bloco cru no evento tipado, ou `null` se for desconhecido.
 *
 * **Tolerar o desconhecido é regra de contrato** (ADR-0008): a evolução é
 * aditiva, e um evento novo que o servidor comece a emitir não pode derrubar um
 * app que está na loja há meses. Ele é ignorado, não é erro.
 */
function traduzir(bloco: Bloco): EventoDoTurn | null {
  if (bloco.id === null || !ehTipoConhecido(bloco.evento)) return null;

  // O `JSON.parse` devolve `any`; a asserção o prende aqui, numa linha só, em
  // vez de deixá-lo vazar para o resto do módulo. Não há validação de runtime
  // de propósito: validar exigiria um validador de schema (zod & cia.), que é
  // dependência nova para um payload que sai do MESMO repositório e cujo
  // formato o `tsc` já cobra dos dois lados (ADR-0008).
  const dados = JSON.parse(bloco.dados) as never;

  return { id: bloco.id, tipo: bloco.evento, dados } as EventoDoTurn;
}

/**
 * Lê o stream do turn e entrega evento a evento, na ordem em que chegam.
 *
 * `async function*` é um **generator assíncrono**: o consumidor escreve
 * `for await (const e of ...)` e recebe cada evento no instante em que ele
 * existe, sem callback e sem fila própria. O equivalente mental em .NET é
 * `IAsyncEnumerable<T>` com `await foreach`.
 *
 * **Quem cancela é o `AbortSignal`** — passado ao `fetch`, ele aborta a conexão
 * de verdade, no nível da requisição. Sem paralelo no React web em um aspecto
 * que importa aqui: no app este mesmo sinal sobrevive à troca de tela, então
 * quem o cria é a máquina de estados, não o componente.
 */
export async function* lerEventos(
  resposta: Response,
  sinal?: AbortSignal,
): AsyncGenerator<EventoDoTurn> {
  const corpo = resposta.body;
  if (!corpo) {
    // Sem stream não há entrega progressiva: o caminho honesto é falhar e deixar
    // o chamador cair para o polling (ADR-0026 item 4), não fingir que funcionou.
    throw new ErroDeStream('a resposta do stream não tem body legível');
  }

  const leitor = corpo.getReader();
  const decodificador = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await leitor.read();
      if (done) break;
      if (sinal?.aborted) return;

      buffer += decodificador.decode(value, { stream: true }).replace(/\r\n/g, '\n');

      // Corta no ÚLTIMO separador completo: o que sobra é um evento pela metade,
      // e emiti-lo daria um `JSON.parse` sobre texto truncado.
      const corte = buffer.lastIndexOf('\n\n');
      if (corte === -1) continue;

      for (const bloco of blocos(buffer.slice(0, corte))) {
        const evento = traduzir(bloco);
        if (evento) yield evento;
      }
      buffer = buffer.slice(corte + 2);
    }
  } finally {
    // `finally` roda também quando o consumidor abandona o `for await` (um
    // `break`, ou o componente desmontando): é o que devolve a conexão em vez de
    // deixá-la pendurada até o timeout de 60 s do servidor.
    await leitor.cancel().catch(() => undefined);
  }
}

/** Falha do transporte do stream — o gatilho para o recuo por polling. */
export class ErroDeStream extends Error {
  constructor(mensagem: string) {
    super(mensagem);
    this.name = 'ErroDeStream';
  }
}
