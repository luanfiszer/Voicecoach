/**
 * O botão cheio, acento sólido, do artboard 11 ("Criar conta"). Reusado nas
 * cinco telas de auth (CARD-050).
 */

import { ActivityIndicator, Pressable, StyleSheet, Text } from 'react-native';

import { alvo, espaco, texto, useCores } from '@/theme/tokens';

type Props = {
  rotulo: string;
  aoTocar: () => void;
  carregando?: boolean;
  desabilitado?: boolean;
};

export function BotaoPrimario({
  rotulo,
  aoTocar,
  carregando = false,
  desabilitado = false,
}: Props) {
  const cores = useCores();
  const inativo = carregando || desabilitado;

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={rotulo}
      accessibilityState={{ disabled: inativo }}
      onPress={inativo ? undefined : aoTocar}
      style={({ pressed }) => [
        estilos.botao,
        {
          backgroundColor: cores.acento,
          opacity: inativo ? 0.6 : pressed ? 0.85 : 1,
        },
      ]}
    >
      {carregando ? (
        <ActivityIndicator color={cores.sobreAcento} />
      ) : (
        <Text style={[texto.corpo, { color: cores.sobreAcento, fontWeight: '700' }]}>
          {rotulo}
        </Text>
      )}
    </Pressable>
  );
}

const estilos = StyleSheet.create({
  botao: {
    minHeight: alvo.minimo + espaco.sm,
    borderRadius: 999,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: espaco.lg,
  },
});
