/**
 * A fronteira nativa do Google Sign-In (CARD-060, ADR-0070) — o único
 * arquivo que importa `@react-native-google-signin/google-signin`.
 *
 * Sem teste próprio, de propósito (ADR-0061): é exatamente a fronteira que
 * o núcleo (`sessaoAutenticada.ts`) existe para não precisar mockar — ele só
 * recebe o `idToken` já extraído, como uma função qualquer.
 */

import {
  GoogleSignin,
  isCancelledResponse,
  isSuccessResponse,
} from '@react-native-google-signin/google-signin';

import { config } from '@/config';

let configurado = false;

function garantirConfigurado(): void {
  if (configurado) return;
  GoogleSignin.configure({ iosClientId: config.googleIosClientId });
  configurado = true;
}

/** O aluno cancelou o próprio fluxo — nunca é falha, a tela volta ao início. */
export class LoginGoogleCancelado extends Error {
  constructor() {
    super('Login com Google cancelado pelo aluno.');
    this.name = 'LoginGoogleCancelado';
  }
}

/**
 * Abre a tela nativa do Google e devolve o `id_token` — o mesmo formato que
 * `Cliente.loginGoogle` espera.
 */
export async function obterIdTokenDoGoogle(): Promise<string> {
  garantirConfigurado();
  await GoogleSignin.hasPlayServices({ showPlayServicesUpdateDialog: false });
  const resposta = await GoogleSignin.signIn();

  if (isCancelledResponse(resposta)) {
    throw new LoginGoogleCancelado();
  }
  if (!isSuccessResponse(resposta)) {
    throw new Error('O Google não devolveu uma resposta reconhecida.');
  }
  const idToken = resposta.data.idToken;
  if (!idToken) {
    throw new Error('O Google não devolveu um id_token.');
  }
  return idToken;
}
