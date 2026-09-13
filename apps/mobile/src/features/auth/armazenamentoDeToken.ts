/**
 * O refresh token em `expo-secure-store` (Keychain/Keystore) — ADR-0007.
 *
 * **Nunca `AsyncStorage`.** `AsyncStorage` é um arquivo de texto puro no
 * sandbox do app; num aparelho comprometido (jailbreak, backup extraído), o
 * refresh de 30 dias estaria em claro. O Keychain/Keystore é criptografado
 * pelo sistema e sobrevive à reinstalação do app (iOS) — comportamento
 * aceitável aqui, porque o servidor é quem revoga de verdade (ADR-0007).
 *
 * Este arquivo não tem teste próprio: é a fronteira NATIVA que
 * `sessaoAutenticada.ts` existe para poder testar sem tocar (ADR-0061) — o
 * dublê da interface `ArmazenamentoDeSessao` é quem carrega a lógica.
 */

import * as SecureStore from 'expo-secure-store';

import type { ArmazenamentoDeSessao } from '@/features/auth/sessaoAutenticada';

const CHAVE_REFRESH_TOKEN = 'voicecoach.refresh_token';

export const armazenamentoSeguro: ArmazenamentoDeSessao = {
  async obterRefreshToken(): Promise<string | null> {
    return SecureStore.getItemAsync(CHAVE_REFRESH_TOKEN);
  },

  async definirRefreshToken(token: string): Promise<void> {
    await SecureStore.setItemAsync(CHAVE_REFRESH_TOKEN, token);
  },

  async limparRefreshToken(): Promise<void> {
    await SecureStore.deleteItemAsync(CHAVE_REFRESH_TOKEN);
  },
};
