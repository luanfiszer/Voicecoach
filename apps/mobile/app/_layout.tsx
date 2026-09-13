/**
 * Layout raiz do `expo-router`.
 *
 * No React web a rota é uma configuração (um `<Route path>`); aqui ela é o
 * SISTEMA DE ARQUIVOS: `app/index.tsx` é `/`, e este `_layout.tsx` envolve
 * tudo que estiver ao lado dele. Não há `<BrowserRouter>` para montar.
 *
 * `headerShown: false` porque a tela desenha o próprio cabeçalho (artboard 01)
 * — o header nativo do Stack é uma segunda barra que o design não tem.
 *
 * **A guarda de sessão mora aqui, fora do `expo-router`** (CARD-050): sem
 * sessão, nenhuma rota do produto é alcançável — não é uma tela a mais no
 * `Stack`, é o que decide se o `Stack` do produto existe. `ProvedorDeSessao`
 * primeiro, para que `useSessao()` funcione em qualquer descendente.
 */

import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { FluxoDeAuth } from '@/features/auth/FluxoDeAuth';
import { TelaDeCarregamento } from '@/features/auth/TelaDeCarregamento';
import { ProvedorDeSessao, useSessao } from '@/features/auth/useSessao';

function ConteudoRaiz() {
  const { estado } = useSessao();

  if (estado === 'carregando') return <TelaDeCarregamento />;
  if (estado === 'nao_autenticado') return <FluxoDeAuth />;
  return <Stack screenOptions={{ headerShown: false }} />;
}

export default function LayoutRaiz() {
  return (
    <SafeAreaProvider>
      <StatusBar style="auto" />
      <ProvedorDeSessao>
        <ConteudoRaiz />
      </ProvedorDeSessao>
    </SafeAreaProvider>
  );
}
