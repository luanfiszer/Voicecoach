/**
 * Layout raiz do `expo-router`.
 *
 * No React web a rota é uma configuração (um `<Route path>`); aqui ela é o
 * SISTEMA DE ARQUIVOS: `app/index.tsx` é `/`, e este `_layout.tsx` envolve
 * tudo que estiver ao lado dele. Não há `<BrowserRouter>` para montar.
 *
 * `headerShown: false` porque a tela desenha o próprio cabeçalho (artboard 01)
 * — o header nativo do Stack é uma segunda barra que o design não tem.
 */

import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';

export default function LayoutRaiz() {
  return (
    <SafeAreaProvider>
      <StatusBar style="auto" />
      <Stack screenOptions={{ headerShown: false }} />
    </SafeAreaProvider>
  );
}
