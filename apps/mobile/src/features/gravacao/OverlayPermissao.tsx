/**
 * O artboard 13, com a microcopy do design intacta.
 *
 * Ele existe por causa do terceiro estado de permissão: no iOS, depois da
 * primeira negação, pedir de novo NÃO abre diálogo — o sistema responde negado
 * na hora. `Linking.openSettings()` é literalmente o único caminho de volta, e
 * é por isso que este overlay não é enfeite: sem ele o app fica sem saída.
 */

import * as Linking from 'expo-linking';
import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';

import { alvo, espaco, texto, useCores } from '@/theme/tokens';

type Props = {
  visivel: boolean;
  aoFechar: () => void;
};

export function OverlayPermissao({ visivel, aoFechar }: Props) {
  const cores = useCores();

  return (
    <Modal visible={visivel} transparent animationType="fade" onRequestClose={aoFechar}>
      <View style={estilos.fundo}>
        <View style={[estilos.cartao, { backgroundColor: cores.fundo }]}>
          <View style={[estilos.icone, { borderColor: cores.acento }]}>
            <View style={[estilos.microfone, { borderColor: cores.acento }]} />
          </View>

          <Text style={[texto.display, { color: cores.tinta }]}>
            Precisamos do microfone
          </Text>
          <Text style={[texto.corpo, estilos.explicacao, { color: cores.secundario }]}>
            O app funciona por voz — sem microfone não há aula. Você pode liberar em
            Ajustes.
          </Text>

          <Pressable
            accessibilityRole="button"
            style={[estilos.botao, { backgroundColor: cores.acento }]}
            onPress={() => void Linking.openSettings()}
          >
            <Text style={[texto.corpo, estilos.rotuloPrimario]}>Abrir Ajustes</Text>
          </Pressable>

          <Pressable
            accessibilityRole="button"
            style={[
              estilos.botao,
              estilos.botaoSecundario,
              { borderColor: cores.secundario },
            ]}
            onPress={aoFechar}
          >
            <Text style={[texto.corpo, { color: cores.tinta }]}>Agora não</Text>
          </Pressable>
        </View>
      </View>
    </Modal>
  );
}

const estilos = StyleSheet.create({
  fundo: {
    flex: 1,
    justifyContent: 'center',
    padding: espaco.lg,
    backgroundColor: 'rgba(0,0,0,0.45)',
  },
  cartao: {
    borderRadius: 28,
    padding: espaco.lg,
    gap: espaco.md,
  },
  icone: {
    width: 52,
    height: 52,
    borderRadius: 16,
    borderWidth: 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  microfone: {
    width: 16,
    height: 26,
    borderRadius: 8,
    borderWidth: 2,
  },
  explicacao: {
    marginTop: -espaco.sm,
  },
  botao: {
    minHeight: alvo.minimo,
    borderRadius: alvo.minimo / 2,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: espaco.lg,
  },
  botaoSecundario: {
    backgroundColor: 'transparent',
    borderWidth: 1,
  },
  rotuloPrimario: {
    color: '#FFFFFF',
    fontWeight: '600',
  },
});
