/**
 * Perfil — placeholder deliberado (CARD-029, artboard 12 fora do escopo).
 *
 * A tela de verdade (saldo de cota, conta) depende da autenticação da Fase 3
 * (CARD-049/050), que não existe ainda. A ABA existe porque o artboard 10
 * mostra as três — "Falar · Histórico · Perfil" — e o critério de aceite do
 * card pede as três presentes; o CONTEÚDO fica deliberadamente vazio até a
 * dependência chegar. Não é implementação pela metade: é a aba certa, com a
 * tela certa para o que existe hoje.
 */

import { StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { espaco, texto, useCores } from '@/theme/tokens';

export default function Rota() {
  const cores = useCores();

  return (
    <SafeAreaView style={[estilos.tela, { backgroundColor: cores.fundo }]}>
      <View style={estilos.conteudo}>
        <Text style={[texto.display, { color: cores.tinta }]}>Perfil</Text>
        <Text style={[texto.apoio, { color: cores.secundario }]}>
          Em breve — depende de login (Fase 3).
        </Text>
      </View>
    </SafeAreaView>
  );
}

const estilos = StyleSheet.create({
  tela: { flex: 1 },
  conteudo: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: espaco.xs,
  },
});
