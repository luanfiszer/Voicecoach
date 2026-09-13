/**
 * O campo de formulário do artboard 11: rótulo em cima, caixa branca
 * arredondada, erro inline em vermelho-acento com o mesmo texto do style
 * guide. Primeira tela do app com `TextInput` — extraído aqui porque cinco
 * telas de auth (CARD-050) o repetem, e o artboard já desenha um padrão
 * único a seguir.
 */

import { useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { alvo, espaco, texto, useCores } from '@/theme/tokens';

type Props = {
  rotulo: string;
  valor: string;
  aoMudar: (valor: string) => void;
  erro?: string | null;
  senha?: boolean;
  tipoDeTeclado?: 'default' | 'email-address';
};

export function CampoDeTexto({
  rotulo,
  valor,
  aoMudar,
  erro,
  senha = false,
  tipoDeTeclado = 'default',
}: Props) {
  const cores = useCores();
  const [mostrarSenha, setMostrarSenha] = useState(false);

  return (
    <View style={estilos.bloco}>
      <Text style={[texto.apoio, { color: cores.secundario }]}>{rotulo}</Text>
      <View
        style={[
          estilos.caixa,
          {
            backgroundColor: cores.superficie,
            borderColor: erro ? cores.acento : 'transparent',
          },
        ]}
      >
        <TextInput
          value={valor}
          onChangeText={aoMudar}
          secureTextEntry={senha && !mostrarSenha}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType={tipoDeTeclado}
          style={[texto.corpo, estilos.entrada, { color: cores.tinta }]}
          placeholderTextColor={cores.secundario}
        />
        {senha ? (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={mostrarSenha ? 'Ocultar senha' : 'Mostrar senha'}
            onPress={() => setMostrarSenha((atual) => !atual)}
            hitSlop={espaco.sm}
          >
            <Text style={[texto.apoio, { color: cores.acento, fontWeight: '600' }]}>
              {mostrarSenha ? 'ocultar' : 'mostrar'}
            </Text>
          </Pressable>
        ) : null}
      </View>
      {erro ? <Text style={[texto.apoio, { color: cores.acento }]}>{erro}</Text> : null}
    </View>
  );
}

const estilos = StyleSheet.create({
  bloco: {
    gap: espaco.xs,
  },
  caixa: {
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: 14,
    borderWidth: 1.5,
    paddingHorizontal: espaco.md,
    minHeight: alvo.minimo,
  },
  entrada: {
    flex: 1,
    paddingVertical: espaco.sm,
  },
});
