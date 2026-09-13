/**
 * As quatro telas de exceção (CARD-027, artboards 14/15/16) — extraídas para
 * serem testáveis sem montar componente (ADR-0061).
 *
 * **O Problem Details é o discriminador, nunca a mensagem** (ADR-0040): este
 * módulo compara `ErroDaApi.tipo` (a URN) contra as duas constantes abaixo, e
 * usa `erro.detalhe` (o texto que o SERVIDOR já escreveu para o aluno) como
 * corpo — não reescreve a explicação, porque o servidor é quem sabe se a
 * cota renova à meia-noite ou se o teto mudou.
 *
 * **As URNs não são geradas** (diferente de `schema.d.ts`): o campo `type` do
 * Problem Details é tipado como `string` solto no OpenAPI (ADR-0040 não gera
 * enum para ele), então esta é a fonte que pode sair de sincronia com
 * `backend/src/voicecoach/api/schemas/problem.py` se uma URN mudar lá. Tolerar
 * o desconhecido é a defesa: uma URN não reconhecida aqui cai no fallback
 * genérico de `estado === 'falhou'` que o app já tinha antes deste card — não
 * uma tela quebrada.
 */

import { ErroDaApi, ErroDeRede } from '@voicecoach/api-client';

/** `backend/.../schemas/problem.py:TYPE_DAILY_QUOTA_EXCEEDED` (ADR-0063). */
export const URN_COTA_DIARIA_ESGOTADA = 'urn:voicecoach:problem:daily-quota-exceeded';
/** `backend/.../schemas/problem.py:TYPE_SERVICE_BUDGET_EXCEEDED` (ADR-0063). */
export const URN_SERVICO_PAUSADO = 'urn:voicecoach:problem:service-budget-exceeded';

export type ConteudoDeExcecao =
  | { tipo: 'offline' }
  | { tipo: 'cota'; mensagem: string }
  | { tipo: 'pausado'; mensagem: string }
  | { tipo: 'travado'; turnId: string; segundos: number };

/**
 * Traduz o que `enviarTurn`/`acompanharTurn` jogaram fora — nunca chame com
 * outra coisa que não veio de lá.
 *
 * `null` é o caminho comum: a MAIORIA dos erros (validação, formato de áudio,
 * turn não encontrado) não tem tela própria neste card — o texto genérico de
 * "algo deu errado" que o app já mostra continua certo para eles. Este card
 * cobre os quatro casos que TÊM ação própria, não todo erro possível.
 */
export function conteudoDoErro(erro: unknown): ConteudoDeExcecao | null {
  if (erro instanceof ErroDeRede) return { tipo: 'offline' };

  if (erro instanceof ErroDaApi) {
    if (erro.tipo === URN_COTA_DIARIA_ESGOTADA) {
      return { tipo: 'cota', mensagem: erro.detalhe ?? MENSAGEM_COTA_PADRAO };
    }
    if (erro.tipo === URN_SERVICO_PAUSADO) {
      return { tipo: 'pausado', mensagem: erro.detalhe ?? MENSAGEM_PAUSADO_PADRAO };
    }
  }

  return null;
}

/** Só usada se o servidor um dia mandar a URN sem `detail` — não deveria. */
export const MENSAGEM_COTA_PADRAO =
  'Você atingiu o limite de uso de hoje. A cota renova à meia-noite.';
export const MENSAGEM_PAUSADO_PADRAO =
  'O serviço atingiu o limite de uso do período. Tente novamente mais tarde.';

export function conteudoDoTravamento(
  turnId: string,
  segundos: number,
): ConteudoDeExcecao {
  return { tipo: 'travado', turnId, segundos };
}

/** Os textos fixos de cada tela — os que o Problem Details não fornece. */
export const TITULOS: Record<ConteudoDeExcecao['tipo'], string> = {
  offline: 'Sua fala está guardada aqui',
  cota: 'Por hoje é isso',
  pausado: 'As aulas estão pausadas',
  travado: 'Demorou mais que o normal',
};

export const MENSAGEM_OFFLINE =
  'Não conseguimos enviar o áudio agora. Toque em tentar de novo quando a conexão voltar.';

export function mensagemDeTravamento(segundos: number): string {
  return `Sua fala foi enviada, mas a resposta não chegou em ${segundos}s. Sua gravação não foi perdida.`;
}
