/**
 * Os textos e formatos da tela de Histórico (CARD-029/030, artboard 10) —
 * extraídos para serem testáveis sem montar componente (ADR-0061).
 *
 * **Sem `Intl`, de propósito.** `toLocaleDateString('pt-BR')` funcionaria aqui
 * em Node, mas o Hermes do React Native não garante ICU completo — o mesmo
 * risco que a skill do cliente registra para qualquer suposição de plataforma
 * não verificada. Uma tabela de meses escrita à mão é determinística nos dois
 * runtimes, e é o que este arquivo testa.
 *
 * **"Hoje"/"Ontem" comparam DIA-CALENDÁRIO local**, não janela de 24h: uma
 * sessão de ontem às 23h50 vista às 00h10 de hoje é "Ontem", não "hoje menos
 * 20 minutos" — é assim que um humano lê a própria agenda.
 */

const MESES = [
  'jan',
  'fev',
  'mar',
  'abr',
  'mai',
  'jun',
  'jul',
  'ago',
  'set',
  'out',
  'nov',
  'dez',
] as const;

function mesmoDiaCalendario(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

/** "Hoje", "Ontem", ou "12 ago" — nunca ano (a janela do card é de 30 dias). */
export function rotuloDoDia(quando: Date, agora: Date): string {
  if (mesmoDiaCalendario(quando, agora)) return 'Hoje';

  const ontem = new Date(agora);
  ontem.setDate(ontem.getDate() - 1);
  if (mesmoDiaCalendario(quando, ontem)) return 'Ontem';

  return `${quando.getDate()} ${MESES[quando.getMonth()]}`;
}

/** "9:12" — hora sem zero à esquerda, minuto com. Relógio de 24h do artboard. */
export function formatarHora(quando: Date): string {
  const minuto = quando.getMinutes().toString().padStart(2, '0');
  return `${quando.getHours()}:${minuto}`;
}

/** "Hoje · 9:12" — o cabeçalho de cada card da lista. */
export function cabecalhoDaSessao(startedAtIso: string, agora: Date): string {
  const quando = new Date(startedAtIso);
  return `${rotuloDoDia(quando, agora)} · ${formatarHora(quando)}`;
}

/**
 * "8:12" — minutos:segundos, a MESMA forma que o resumo pós-sessão promete
 * (CARD-031). Sem hora: `max_turn_audio_duration` é 120s por turn e a cota
 * diária é de minutos — nenhuma sessão real passa de 59:59 hoje, e o dia em
 * que passar, o card certo é o que decide horas, não este.
 */
export function formatarDuracao(segundosFalados: number): string {
  const total = Math.max(0, Math.round(segundosFalados));
  const minutos = Math.floor(total / 60);
  const segundos = (total % 60).toString().padStart(2, '0');
  return `${minutos}:${segundos}`;
}

function pluralizar(quantidade: number, singular: string, plural: string): string {
  return `${quantidade} ${quantidade === 1 ? singular : plural}`;
}

/** "5 correções" / "1 correção". */
export function rotuloDeCorrecoes(quantidade: number): string {
  return pluralizar(quantidade, 'correção', 'correções');
}

/** "7 turnos" / "1 turno". */
export function rotuloDeTurnos(quantidade: number): string {
  return pluralizar(quantidade, 'turno', 'turnos');
}

/** A nota de rodapé, fixa — a promessa que o artboard imprime uma vez só. */
export const NOTA_DA_JANELA = 'Sessões anteriores a 30 dias vivem no app web';

/** O texto do aviso quando o áudio já não está disponível (ADR-0024/0067). */
export const AVISO_DE_AUDIO_EXPIRADO =
  'Áudio expirado — transcrição e correções permanecem';
