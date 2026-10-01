/**
 * Os textos da cota do dia (artboard 12, ADR-0064) — testáveis sem DOM.
 *
 * `blocked_reason` é a chave do que dizer (nunca dólares, RF4 do CARD-033):
 * os três motivos têm frases diferentes de propósito.
 */

import type { CotaDoDia } from '@voicecoach/api-client';

/** "4 de 10 min" — minutos inteiros, arredondando o falado para baixo. */
export function rotuloDoSaldo(
  cota: Pick<CotaDoDia, 'spoken_seconds' | 'quota_spoken_seconds'>,
): string {
  const falado = Math.floor(Math.max(0, cota.spoken_seconds) / 60);
  const teto = Math.round(cota.quota_spoken_seconds / 60);
  return `${Math.min(falado, teto)} de ${teto} min`;
}

/** Fração de 0 a 1 para a barra — nunca passa de 1, mesmo se o falado passar. */
export function fracaoUsada(
  cota: Pick<CotaDoDia, 'spoken_seconds' | 'quota_spoken_seconds'>,
): number {
  if (cota.quota_spoken_seconds <= 0) return 1;
  return Math.min(1, Math.max(0, cota.spoken_seconds / cota.quota_spoken_seconds));
}

/** "Renova às 0:00" — a virada no relógio LOCAL de quem lê. */
export function rotuloDaVirada(resetsAtIso: string): string {
  const quando = new Date(resetsAtIso);
  const minuto = quando.getMinutes().toString().padStart(2, '0');
  return `Renova às ${quando.getHours()}:${minuto}`;
}

/** O que dizer quando o aluno não pode falar agora; `null` quando pode. */
export function mensagemDeBloqueio(motivo: CotaDoDia['blocked_reason']): string | null {
  switch (motivo) {
    case null:
    case undefined:
      return null;
    case 'daily_minutes':
      return 'Por hoje é isso — você usou todos os minutos de fala do dia.';
    case 'many_short_turns':
      return 'Muitas falas curtas hoje. A cota renova à meia-noite.';
    case 'service_paused':
      return 'As aulas estão pausadas no momento. Tente novamente mais tarde.';
  }
}
