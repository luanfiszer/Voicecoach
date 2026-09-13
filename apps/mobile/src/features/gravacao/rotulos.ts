/**
 * Os textos da tela de conversa — extraídos para serem testáveis (ADR-0061).
 *
 * **CARD-028 fecha aqui uma decisão que o CARD-012 já tinha tomado na prática,
 * sem registro formal.** Os artboards 03–06 (`docs/design/README.md`)
 * descrevem "Passo 1 de 3", uma etapa própria de "professor pensando" e a
 * ordem texto-depois-áudio — todos anteriores à cascata (ADR-0022/0023) e
 * incompatíveis com ela. Nenhum sobrevive aqui: `subtitulo` nunca enumera
 * passo, nunca promete progresso proporcional, e o estado `ouvindo` tem texto
 * PRÓPRIO ("o professor está falando") — não um genérico herdado de
 * `transcrevendo`.
 */

import type { EstadoDoTurn } from '@/features/turno/useTurno';

/**
 * O subtítulo do cabeçalho — **a etapa da cascata, não a do desenho antigo**.
 *
 * Os artboards 03–06 descrevem uma sequência anterior à cascata (transcrevendo →
 * pensando → texto → áudio). Hoje o áudio começa antes de o texto do feedback
 * fechar (ADR-0022/0023), e o vocabulário aqui reflete a ordem real.
 */
export function subtitulo(gravando: boolean, turno: EstadoDoTurn): string {
  if (gravando) return 'Gravando…';
  switch (turno) {
    case 'ocioso':
      return 'Nenhum turno ainda';
    case 'enviando':
      return 'Enviando…';
    case 'transcrevendo':
      return 'Transcrevendo…';
    case 'ouvindo':
      return 'O professor está falando…';
    case 'concluido':
      return 'Sua vez';
    case 'falhou':
      return 'Algo deu errado';
  }
}

export function rotulo(estado: 'ocioso' | 'gravando' | 'gravado'): string {
  switch (estado) {
    case 'ocioso':
      return 'Toque para falar';
    case 'gravando':
      return 'Toque para parar';
    // O rótulo descreve o BOTÃO, não o player: no estado `gravado` o botão
    // grava de novo. "Ouça o que você falou" ficava embaixo dele e sugeria
    // que tocá-lo reproduziria o áudio.
    case 'gravado':
      return 'Toque para gravar de novo';
  }
}
