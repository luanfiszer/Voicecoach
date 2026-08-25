/**
 * Ouvir o que acabou de ser gravado, sem sair da tela (critério de aceite).
 *
 * Este player é **local e provisório por natureza**: ele toca um arquivo do
 * sistema de arquivos do aparelho. O player do produto toca 3–6 TRECHOS em
 * sequência, vindos de URL assinada (ADR-0023/0024) — isso é CARD-012, e o
 * artboard 06 (um player, uma duração) descreve o produto de antes da cascata.
 *
 * O componente é montado com `key={uri}`: `useAudioPlayer` prende um objeto
 * nativo à fonte que recebeu no primeiro render, então trocar de gravação é
 * trocar de player, não mutar o que existe.
 */

import { useAudioPlayer, useAudioPlayerStatus } from 'expo-audio';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { alvo, espaco, texto, useCores } from '@/theme/tokens';

type Props = {
  uri: string;
};

export function PlayerLocal({ uri }: Props) {
  const cores = useCores();
  const player = useAudioPlayer({ uri });
  const status = useAudioPlayerStatus(player);

  const tocando = status.playing;

  return (
    <View style={[estilos.caixa, { backgroundColor: cores.superficie }]}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={tocando ? 'Pausar' : 'Ouvir o que gravei'}
        style={[estilos.play, { backgroundColor: cores.acento }]}
        onPress={() => {
          if (tocando) {
            player.pause();
            return;
          }
          // Quando o áudio já terminou, `play()` sozinho não rebobina.
          if (status.didJustFinish || status.currentTime >= status.duration) {
            player.seekTo(0);
          }
          player.play();
        }}
      >
        {tocando ? <View style={estilos.pausa} /> : <View style={estilos.triangulo} />}
      </Pressable>

      <Text style={[texto.apoio, { color: cores.secundario }]}>
        {formatar(status.currentTime)} / {formatar(status.duration)}
      </Text>
    </View>
  );
}

function formatar(segundos: number): string {
  if (!Number.isFinite(segundos) || segundos < 0) return '0:00';
  const total = Math.floor(segundos);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

const estilos = StyleSheet.create({
  caixa: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: espaco.md,
    paddingVertical: espaco.sm,
    paddingHorizontal: espaco.md,
    borderRadius: alvo.minimo,
  },
  play: {
    width: alvo.minimo,
    height: alvo.minimo,
    borderRadius: alvo.minimo / 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  triangulo: {
    marginLeft: 4,
    width: 0,
    height: 0,
    borderTopWidth: 9,
    borderBottomWidth: 9,
    borderLeftWidth: 15,
    borderTopColor: 'transparent',
    borderBottomColor: 'transparent',
    borderLeftColor: '#FFFFFF',
  },
  pausa: {
    width: 14,
    height: 16,
    borderLeftWidth: 4,
    borderRightWidth: 4,
    borderColor: '#FFFFFF',
  },
});
