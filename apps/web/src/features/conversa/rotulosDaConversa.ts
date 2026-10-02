/**
 * Os textos da conversa na web (CARD-065) — testáveis sem DOM (ADR-0061).
 *
 * Os de correção e tradução são cópias do mobile (`rotulosDeCorrecao.ts`,
 * `rotuloDaTraducao.ts`; ADR-0002). Os de recusa são NOVOS: o mobile ainda
 * não trata o evento `rejected` (lacuna registrada no CARD-065).
 */

import type { components } from '@voicecoach/api-client';

export type TipoDeCorrecao = components['schemas']['CorrectionType'];
export type Severidade = components['schemas']['Severity'];
export type MotivoDeRecusa = components['schemas']['RejectionReason'];

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

/**
 * A recusa é um CONVITE a repetir, não uma tela de erro (ADR-0057). O tom vem
 * do título do CARD-040: *"Não entendi, pode repetir?"*.
 */
export function mensagemDeRecusa(motivo: MotivoDeRecusa): string {
  switch (motivo) {
    case 'low_confidence':
      return 'Não entendi, pode repetir?';
    case 'no_speech':
      return 'Não ouvi nada. Pode repetir, um pouco mais perto do microfone?';
    case 'not_english':
      return 'Isso não pareceu inglês. Pode repetir em inglês?';
  }
}

export type FaseDaTraducao = 'ocioso' | 'traduzindo' | 'traduzido' | 'falhou';

export function rotuloDoBotaoDeTraduzir(fase: FaseDaTraducao): string {
  switch (fase) {
    case 'traduzindo':
      return 'Traduzindo…';
    case 'falhou':
      return 'A tradução falhou — tentar de novo';
    case 'ocioso':
    case 'traduzido':
      return 'Traduzir';
  }
}

/** O subtítulo da tela, pelo momento da conversa. */
export function subtitulo(gravando: boolean, estado: EstadoDaConversa): string {
  if (gravando) return 'Gravando… clique de novo para enviar.';
  switch (estado) {
    case 'enviando':
      return 'Enviando sua fala…';
    case 'transcrevendo':
      return 'Ouvindo o que você disse…';
    case 'ouvindo':
      return 'O professor está respondendo.';
    case 'ocioso':
    case 'concluido':
    case 'recusado':
    case 'falhou':
      return 'Clique no botão e fale em inglês.';
  }
}

export type EstadoDaConversa =
  | 'ocioso'
  | 'enviando'
  | 'transcrevendo'
  | 'ouvindo'
  | 'concluido'
  | 'recusado'
  | 'falhou';

/** "0:07 / 1:30" — o relógio da gravação. */
export function formatarRelogio(segundos: number): string {
  const total = Math.max(0, Math.floor(segundos));
  return `${Math.floor(total / 60)}:${(total % 60).toString().padStart(2, '0')}`;
}
