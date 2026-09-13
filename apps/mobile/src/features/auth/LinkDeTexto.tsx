/**
 * O link de texto do artboard 11 ("Já tem conta? **Entrar**") — acento,
 * negrito, sem sublinhado. Reusado nas cinco telas de auth (CARD-050).
 */

import { Pressable, Text } from 'react-native';

import { espaco, texto, useCores } from '@/theme/tokens';

type Props = {
  rotulo: string;
  aoTocar: () => void;
};

export function LinkDeTexto({ rotulo, aoTocar }: Props) {
  const cores = useCores();

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={rotulo}
      onPress={aoTocar}
      hitSlop={espaco.sm}
    >
      <Text style={[texto.apoio, { color: cores.acento, fontWeight: '700' }]}>
        {rotulo}
      </Text>
    </Pressable>
  );
}
