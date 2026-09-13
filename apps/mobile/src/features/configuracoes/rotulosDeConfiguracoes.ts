/**
 * Os textos da tela de Configurações (CARD-059) — extraídos para serem
 * testáveis sem montar componente (ADR-0061).
 */

/**
 * "1 min 30 s" / "45 s" / "2 min" — por extenso, porque esta tela é
 * informativa (o valor não é editável), não um relógio de leitura rápida
 * como `formatarDuracao` do histórico.
 */
export function rotuloDoLimiteDeGravacao(segundos: number): string {
  const total = Math.max(0, Math.round(segundos));
  const minutos = Math.floor(total / 60);
  const resto = total % 60;

  if (minutos === 0) return `${resto} s`;
  if (resto === 0) return `${minutos} min`;
  return `${minutos} min ${resto} s`;
}
