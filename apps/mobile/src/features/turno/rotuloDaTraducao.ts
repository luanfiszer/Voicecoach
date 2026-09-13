/**
 * O rótulo do botão `traduzir` (CARD-058), por fase — extraído para ser
 * testável sem `Text`/`Pressable` nativos, mesmo padrão de
 * `rotulosDeCorrecao.ts` (ADR-0061).
 */

import type { FaseDaTraducao } from '@/features/turno/useTurno';

export function rotuloDoBotaoDeTraduzir(fase: FaseDaTraducao): string {
  switch (fase) {
    case 'traduzindo':
      return 'TRADUZINDO…';
    case 'falhou':
      return 'TRADUÇÃO FALHOU — TOCAR PARA TENTAR DE NOVO';
    case 'ocioso':
    case 'traduzido':
      return 'TRADUZIR';
  }
}
