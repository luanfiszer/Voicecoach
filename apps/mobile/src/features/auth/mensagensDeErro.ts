/**
 * Traduz o que as cinco telas de auth (CARD-050) recebem do servidor numa
 * frase para o aluno — extraído para ser testável sem montar nenhuma tela
 * (ADR-0061), mesmo padrão de `conteudoDaExcecao.ts` (CARD-027).
 *
 * **`tipo` é a chave semântica**, nunca `detalhe`/`title` (ADR-0040) — é por
 * isso que só os dois tipos que o aluno precisa distinguir de verdade
 * (credenciais erradas, rate limit) têm mensagem própria; o resto usa o
 * `detalhe` que o Problem Details já trouxe.
 */

import { ErroDaApi, ErroDeRede } from '@voicecoach/api-client';

const TYPE_INVALID_CREDENTIALS = 'urn:voicecoach:problem:invalid-credentials';
const TYPE_RATE_LIMITED = 'urn:voicecoach:problem:rate-limited';

export function mensagemDeErroDeAuth(erro: unknown): string {
  if (erro instanceof ErroDeRede) {
    return 'Não foi possível falar com o servidor. Verifique sua conexão.';
  }
  if (erro instanceof ErroDaApi) {
    if (erro.tipo === TYPE_INVALID_CREDENTIALS) return 'E-mail ou senha incorretos.';
    if (erro.tipo === TYPE_RATE_LIMITED) {
      return 'Muitas tentativas seguidas. Espere um pouco e tente de novo.';
    }
    return erro.detalhe ?? erro.message;
  }
  return 'Algo deu errado. Tente de novo.';
}
