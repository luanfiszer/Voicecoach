/**
 * O que as telas de auth recebem do servidor, numa frase para o aluno — o
 * MESMO texto do mobile (`apps/mobile/src/features/auth/mensagensDeErro.ts`),
 * duplicado de propósito: as duas UIs não compartilham código (ADR-0002).
 * `tipo` é a chave semântica (ADR-0040), nunca o `title`.
 */

import { ErroDaApi, ErroDeRede } from '@voicecoach/api-client';

const TYPE_INVALID_CREDENTIALS = 'urn:voicecoach:problem:invalid-credentials';
const TYPE_RATE_LIMITED = 'urn:voicecoach:problem:rate-limited';
const TYPE_DEPENDENCY_UNAVAILABLE = 'urn:voicecoach:problem:dependency-unavailable';

export function mensagemDeErro(erro: unknown): string {
  if (erro instanceof ErroDeRede) {
    return 'Não foi possível falar com o servidor. Verifique sua conexão.';
  }
  if (erro instanceof ErroDaApi) {
    if (erro.tipo === TYPE_INVALID_CREDENTIALS) return 'E-mail ou senha incorretos.';
    if (erro.tipo === TYPE_RATE_LIMITED) {
      return 'Muitas tentativas seguidas. Espere um pouco e tente de novo.';
    }
    if (erro.tipo === TYPE_DEPENDENCY_UNAVAILABLE) {
      return 'O serviço está instável agora. Tente de novo em instantes.';
    }
    return erro.detalhe ?? erro.message;
  }
  return 'Algo deu errado. Tente de novo.';
}
