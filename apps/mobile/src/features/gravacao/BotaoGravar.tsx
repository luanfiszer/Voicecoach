/**
 * O botão de 84px do style guide: **pulso = gravando, quadrado = parar**.
 *
 * O estado "gravando" NÃO tem artboard — o design não o entregou (registrado em
 * `docs/design/README.md`). Ele é derivado do que existe: os 84px, o acento, o
 * pulso e o quadrado. Nada inventado além disso.
 *
 * `Animated` é o do próprio React Native, não `reanimated`: um pulso é uma
 * escala em loop, e trazer uma biblioteca de animação para isso contraria a
 * Parte F da visão (sem peça nova sem gatilho).
 */

import { useEffect, useRef } from 'react';
import { Animated, Easing, Pressable, StyleSheet, View } from 'react-native';

import { alvo, useCores } from '@/theme/tokens';

type Props = {
  gravando: boolean;
  /** dBFS do microfone, ou `null`. Escala o halo — é o "nível de áudio". */
  nivel: number | null;
  aoTocar: () => void;
};

export function BotaoGravar({ gravando, nivel, aoTocar }: Props) {
  const cores = useCores();
  const pulso = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (!gravando) {
      pulso.setValue(0);
      return;
    }
    const ciclo = Animated.loop(
      Animated.sequence([
        Animated.timing(pulso, {
          toValue: 1,
          duration: 900,
          easing: Easing.out(Easing.ease),
          useNativeDriver: true,
        }),
        Animated.timing(pulso, {
          toValue: 0,
          duration: 900,
          easing: Easing.in(Easing.ease),
          useNativeDriver: true,
        }),
      ]),
    );
    ciclo.start();
    return () => ciclo.stop();
  }, [gravando, pulso]);

  // dBFS vai de ~-60 (silêncio) a 0 (saturado). Vira 0..1 para o halo.
  const intensidade = nivel === null ? 0 : Math.min(1, Math.max(0, (nivel + 60) / 60));

  return (
    <View style={estilos.area}>
      {gravando ? (
        <Animated.View
          pointerEvents="none"
          style={[
            estilos.halo,
            {
              backgroundColor: cores.acento,
              opacity: pulso.interpolate({
                inputRange: [0, 1],
                outputRange: [0.22, 0.06],
              }),
              transform: [
                {
                  scale: pulso.interpolate({
                    inputRange: [0, 1],
                    outputRange: [1, 1.35 + intensidade * 0.35],
                  }),
                },
              ],
            },
          ]}
        />
      ) : null}

      <Pressable
        accessibilityRole="button"
        accessibilityLabel={gravando ? 'Parar de gravar' : 'Gravar'}
        onPress={aoTocar}
        style={({ pressed }) => [
          estilos.botao,
          { backgroundColor: cores.acento, opacity: pressed ? 0.85 : 1 },
        ]}
      >
        {gravando ? (
          <View style={estilos.quadrado} />
        ) : (
          <View style={estilos.microfone} />
        )}
      </Pressable>
    </View>
  );
}

const estilos = StyleSheet.create({
  area: {
    width: alvo.gravar * 2,
    height: alvo.gravar * 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  halo: {
    position: 'absolute',
    width: alvo.gravar,
    height: alvo.gravar,
    borderRadius: alvo.gravar / 2,
  },
  botao: {
    width: alvo.gravar,
    height: alvo.gravar,
    borderRadius: alvo.gravar / 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  microfone: {
    width: 22,
    height: 34,
    borderRadius: 11,
    borderWidth: 2.5,
    borderColor: '#FFFFFF',
  },
  quadrado: {
    width: 26,
    height: 26,
    borderRadius: 5,
    backgroundColor: '#FFFFFF',
  },
});
