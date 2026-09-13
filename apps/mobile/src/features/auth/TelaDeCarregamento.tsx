/**
 * O intervalo entre "o app abriu" e "sabemos se há sessão" (CARD-050) —
 * o `inicializar()` de `sessaoAutenticada.ts` tentando o refresh silencioso.
 * Sem artboard: é um estado técnico, não um momento do produto.
 */

import { ActivityIndicator, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useCores } from '@/theme/tokens';

export function TelaDeCarregamento() {
  const cores = useCores();

  return (
    <SafeAreaView style={[estilos.tela, { backgroundColor: cores.fundo }]}>
      <View style={estilos.conteudo}>
        <ActivityIndicator color={cores.acento} size="large" />
      </View>
    </SafeAreaView>
  );
}

const estilos = StyleSheet.create({
  tela: { flex: 1 },
  conteudo: { flex: 1, alignItems: 'center', justifyContent: 'center' },
});
