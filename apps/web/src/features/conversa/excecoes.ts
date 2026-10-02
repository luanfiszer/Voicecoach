/**
 * As telas que cobrem a conversa (artboards 14/15/16; CARD-027) — o
 * `conteudoDaExcecao.ts` do mobile, na web. A URN do Problem Details é o
 * discriminador (ADR-0040); o corpo é o `detail` que o servidor escreveu.
 */

import { ErroDaApi, ErroDeRede } from '@voicecoach/api-client';

const URN_COTA = 'urn:voicecoach:problem:daily-quota-exceeded';
const URN_PAUSADO = 'urn:voicecoach:problem:service-budget-exceeded';

export type Excecao =
  | { tipo: 'offline' }
  | { tipo: 'cota'; mensagem: string }
  | { tipo: 'pausado'; mensagem: string }
  | { tipo: 'travado'; segundos: number };

export function excecaoDoErro(erro: unknown): Excecao | null {
  if (erro instanceof ErroDeRede) return { tipo: 'offline' };
  if (erro instanceof ErroDaApi) {
    if (erro.tipo === URN_COTA) {
      return {
        tipo: 'cota',
        mensagem:
          erro.detalhe ??
          'Você atingiu o limite de uso de hoje. A cota renova à meia-noite.',
      };
    }
    if (erro.tipo === URN_PAUSADO) {
      return {
        tipo: 'pausado',
        mensagem:
          erro.detalhe ??
          'O serviço atingiu o limite de uso do período. Tente novamente mais tarde.',
      };
    }
  }
  return null;
}

export const TITULOS: Record<Excecao['tipo'], string> = {
  offline: 'Sua fala está guardada aqui',
  cota: 'Por hoje é isso',
  pausado: 'As aulas estão pausadas',
  travado: 'Demorou mais que o normal',
};

export function corpoDaExcecao(excecao: Excecao): string {
  switch (excecao.tipo) {
    case 'offline':
      return 'Não conseguimos enviar o áudio agora. Tente de novo quando a conexão voltar.';
    case 'cota':
    case 'pausado':
      return excecao.mensagem;
    case 'travado':
      return `Sua fala foi enviada, mas a resposta não chegou em ${excecao.segundos}s. Sua gravação não foi perdida.`;
  }
}
