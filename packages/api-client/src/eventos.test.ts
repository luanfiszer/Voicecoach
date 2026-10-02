/**
 * O leitor do `text/event-stream` (ADR-0026/0046) — sem teste próprio até o
 * CARD-065, quando o `rejected` entrou. O que se fixa: os eventos tipados saem
 * na ordem do fio, o `rejected` é reconhecido, e evento desconhecido continua
 * ignorado (evolução aditiva, ADR-0008).
 */

import { describe, expect, it } from 'vitest';

import { type EventoDoTurn, lerEventos } from './eventos';

function respostaDeStream(texto: string): Response {
  const bytes = new TextEncoder().encode(texto);
  // Dois pedaços, cortando um evento no meio: o leitor tem de remontá-lo.
  const meio = Math.floor(bytes.length / 2);
  const corpo = new ReadableStream<Uint8Array>({
    start(controlador) {
      controlador.enqueue(bytes.slice(0, meio));
      controlador.enqueue(bytes.slice(meio));
      controlador.close();
    },
  });
  return new Response(corpo, { headers: { 'content-type': 'text/event-stream' } });
}

async function coletar(resposta: Response): Promise<EventoDoTurn[]> {
  const eventos: EventoDoTurn[] = [];
  for await (const evento of lerEventos(resposta)) eventos.push(evento);
  return eventos;
}

describe('lerEventos', () => {
  it('reconhece o rejected (CARD-040) e ignora evento que não conhece', async () => {
    const fio = [
      'id: transcribed\nevent: transcribed\ndata: {"transcript":"eu falei portugues"}\n\n',
      ': keep-alive\n\n',
      'id: futuro\nevent: algo_novo_do_servidor\ndata: {}\n\n',
      'id: rejected\nevent: rejected\ndata: {"reason":"not_english"}\n\n',
    ].join('');

    const eventos = await coletar(respostaDeStream(fio));

    expect(eventos.map((e) => e.tipo)).toEqual(['transcribed', 'rejected']);
    const recusa = eventos[1];
    expect(recusa?.tipo === 'rejected' && recusa.dados.reason).toBe('not_english');
  });
});
