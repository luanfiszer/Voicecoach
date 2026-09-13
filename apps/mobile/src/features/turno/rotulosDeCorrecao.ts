/**
 * Os textos pt-BR das correções tipadas (CARD-016) — extraídos, como
 * `rotulos.ts`, para serem testáveis sem montar componente (ADR-0061).
 *
 * `CorrectionType`/`Severity` vêm do contrato gerado (ADR-0008): o `tsc`
 * reprova este arquivo se o backend acrescentar um valor sem que ele seja
 * tratado aqui — o `switch` sem `default` é a exaustividade em modo estrito.
 */

import type { components } from '@voicecoach/api-client';

export type TipoDeCorrecao = components['schemas']['CorrectionType'];
export type Severidade = components['schemas']['Severity'];

export function rotuloDoTipo(tipo: TipoDeCorrecao): string {
  switch (tipo) {
    case 'grammar':
      return 'Gramática';
    case 'vocabulary':
      return 'Vocabulário';
    case 'preposition':
      return 'Preposição';
    case 'word_order':
      return 'Ordem das palavras';
    case 'other':
      return 'Outro';
  }
}

export function rotuloDaSeveridade(severidade: Severidade): string {
  switch (severidade) {
    case 'minor':
      return 'Leve';
    case 'moderate':
      return 'Moderado';
    case 'major':
      return 'Importante';
  }
}

/** O resumo mínimo de sessão (CARD-016): a fundação do resumo da Fase 6. */
export type ResumoDaSessao = {
  total: number;
  porTipo: Partial<Record<TipoDeCorrecao, number>>;
};

export const RESUMO_VAZIO: ResumoDaSessao = { total: 0, porTipo: {} };

/**
 * Uma linha compacta para o cabeçalho — "3 correções: 2 gramática, 1 outro".
 *
 * `null` quando não há nada a mostrar: a regra de produto do protótipo é
 * "sem correção, sem card" (CARD-016), e o resumo segue a mesma — mostrar
 * "0 correções" seria ruído numa sessão que só teve acertos.
 */
export function formatarResumo(resumo: ResumoDaSessao): string | null {
  if (resumo.total === 0) return null;

  const partes = Object.entries(resumo.porTipo)
    // Ordem estável e determinística: por contagem decrescente, depois pelo
    // próprio tipo — sem isso a ordem do `Object.entries` (inserção) faria a
    // mesma sessão renderizar em ordens diferentes dependendo de qual erro
    // apareceu primeiro, só para o mesmo total.
    .sort(([tipoA, a], [tipoB, b]) => b - a || tipoA.localeCompare(tipoB))
    .map(
      ([tipo, quantidade]) => `${quantidade} ${rotuloDoTipo(tipo as TipoDeCorrecao)}`,
    );

  const rotuloTotal = resumo.total === 1 ? 'correção' : 'correções';
  return `${resumo.total} ${rotuloTotal}: ${partes.join(', ')}`;
}
