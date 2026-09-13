/**
 * O CARD-028 fechado em teste: o design anterior à cascata não sobrevive.
 *
 * Cada asserção aqui corresponde a um critério de aceite do card — "nenhum
 * texto de UI enumera passo N de 3" e "o estado de áudio tocando não é
 * spinner genérico" deixam de ser afirmação em markdown e viram invariante
 * que o `vitest` segura.
 */

import { describe, expect, it } from 'vitest';

import type { EstadoDoTurn } from '@/features/turno/useTurno';
import { rotulo, subtitulo } from './rotulos';

const TODOS_OS_ESTADOS: EstadoDoTurn[] = [
  'ocioso',
  'enviando',
  'transcrevendo',
  'ouvindo',
  'concluido',
  'falhou',
];

describe('subtitulo', () => {
  it('nunca enumera "passo N de 3" — o artboard 03 morreu (CARD-028)', () => {
    for (const estado of TODOS_OS_ESTADOS) {
      expect(subtitulo(false, estado)).not.toMatch(/passo/i);
    }
    expect(subtitulo(true, 'ocioso')).not.toMatch(/passo/i);
  });

  it('o estado "ouvindo" tem texto PRÓPRIO — não herda o de "transcrevendo"', () => {
    // O artboard 04 ("professor pensando", passo 2 de 3) morreu como estado
    // próprio: a etapa dura ~0,8s, curta demais para tela dedicada. O app
    // pula direto para "ouvindo" quando o primeiro trecho chega — e o texto
    // desse estado não pode ser um spinner genérico herdado da transcrição.
    const doOuvindo = subtitulo(false, 'ouvindo');
    const doTranscrevendo = subtitulo(false, 'transcrevendo');

    expect(doOuvindo).not.toBe(doTranscrevendo);
    expect(doOuvindo).not.toMatch(/transcrevendo|carregando|aguarde/i);
  });

  it('gravando sempre vence, independente do estado do turn anterior', () => {
    for (const estado of TODOS_OS_ESTADOS) {
      expect(subtitulo(true, estado)).toBe('Gravando…');
    }
  });
});

describe('rotulo', () => {
  it('descreve o botão, não o player — "gravado" convida a gravar de novo', () => {
    // "Ouça o que você falou" ficava embaixo do botão em `gravado` e sugeria
    // que tocá-lo reproduziria o áudio — o botão grava de novo, quem toca é
    // o `PlayerLocal`. Rótulo errado aqui é o tipo de bug que só aparece no
    // dedo de quem usa, nunca em lint nem em tipo.
    expect(rotulo('gravado')).toMatch(/gravar de novo/i);
    expect(rotulo('gravado')).not.toMatch(/ouça|reproduz/i);
  });
});
