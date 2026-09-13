/**
 * Cada asserção aqui corresponde a um pedaço do artboard 10, transcrito em
 * `docs/design/artboards/10-historico.png`: "Hoje · 9:12", "Ontem · 21:40",
 * "12 ago · 7:30", "5 correções", "7 turnos" e o aviso de áudio expirado.
 */

import { describe, expect, it } from 'vitest';
import {
  AVISO_DE_AUDIO_EXPIRADO,
  cabecalhoDaSessao,
  formatarDuracao,
  formatarHora,
  NOTA_DA_JANELA,
  rotuloDeCorrecoes,
  rotuloDeTurnos,
  rotuloDoDia,
} from './rotulosDoHistorico';

const AGORA = new Date(2026, 8, 13, 9, 41); // 13 set 2026, 9:41 — a hora do artboard

describe('rotuloDoDia', () => {
  it('é "Hoje" no mesmo dia-calendário, não importa a hora', () => {
    expect(rotuloDoDia(new Date(2026, 8, 13, 0, 1), AGORA)).toBe('Hoje');
    expect(rotuloDoDia(new Date(2026, 8, 13, 23, 59), AGORA)).toBe('Hoje');
  });

  it('é "Ontem" no dia-calendário anterior — não "24h atrás"', () => {
    // 23h50 de ontem visto às 9:41 de hoje: são só ~10h, mas é "Ontem".
    expect(rotuloDoDia(new Date(2026, 8, 12, 23, 50), AGORA)).toBe('Ontem');
  });

  it('uma sessão de ontem à noite, vista logo depois da meia-noite, é "Ontem"', () => {
    const logoAposAMeiaNoite = new Date(2026, 8, 13, 0, 10);
    expect(rotuloDoDia(new Date(2026, 8, 12, 23, 50), logoAposAMeiaNoite)).toBe(
      'Ontem',
    );
  });

  it('data mais antiga vira "12 ago" — dia e mês abreviado, sem ano', () => {
    expect(rotuloDoDia(new Date(2026, 7, 12, 7, 30), AGORA)).toBe('12 ago');
  });
});

describe('formatarHora', () => {
  it('não põe zero à esquerda na hora, mas põe no minuto', () => {
    expect(formatarHora(new Date(2026, 8, 13, 9, 12))).toBe('9:12');
    expect(formatarHora(new Date(2026, 8, 13, 21, 40))).toBe('21:40');
    expect(formatarHora(new Date(2026, 8, 13, 7, 5))).toBe('7:05');
  });
});

describe('cabecalhoDaSessao', () => {
  it('junta o dia e a hora com " · ", como o artboard', () => {
    const iso = new Date(2026, 8, 13, 9, 12).toISOString();
    expect(cabecalhoDaSessao(iso, AGORA)).toBe('Hoje · 9:12');
  });
});

describe('formatarDuracao', () => {
  it('formata em minutos:segundos, com zero à esquerda no segundo', () => {
    expect(formatarDuracao(492)).toBe('8:12'); // Hoje, no artboard
    expect(formatarDuracao(665)).toBe('11:05'); // Ontem, no artboard
    expect(formatarDuracao(348)).toBe('5:48'); // 12 ago, no artboard
  });

  it('zero segundos falados é "0:00", não ausência', () => {
    expect(formatarDuracao(0)).toBe('0:00');
  });
});

describe('rotuloDeCorrecoes e rotuloDeTurnos', () => {
  it('pluralizam a partir de 2, e usam singular em 1', () => {
    expect(rotuloDeCorrecoes(5)).toBe('5 correções');
    expect(rotuloDeCorrecoes(1)).toBe('1 correção');
    expect(rotuloDeCorrecoes(0)).toBe('0 correções');
    expect(rotuloDeTurnos(7)).toBe('7 turnos');
    expect(rotuloDeTurnos(1)).toBe('1 turno');
  });
});

describe('textos fixos', () => {
  it('a nota de rodapé e o aviso de áudio expirado batem com o artboard', () => {
    expect(NOTA_DA_JANELA).toBe('Sessões anteriores a 30 dias vivem no app web');
    expect(AVISO_DE_AUDIO_EXPIRADO).toBe(
      'Áudio expirado — transcrição e correções permanecem',
    );
  });
});
