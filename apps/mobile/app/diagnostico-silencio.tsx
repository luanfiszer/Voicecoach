/**
 * A rota de diagnóstico do CARD-042 — **o instrumento que mede o silêncio**.
 *
 * **Por que ela existe, e por que ela não precisa de ouvido.** O card pergunta
 * se `player.remove()` sem `pause()` antes cala o som. Medir isso pelo ouvido
 * exige o aparelho e um cronômetro; medir pelo *player* seria impossível, porque
 * é o player que estamos destruindo. Mas existe um terceiro caminho, e ele é
 * legível por máquina:
 *
 * > enquanto o `AVPlayer` nativo estiver **vivo e tocando**, o time observer
 * > instalado nele continua emitindo `playbackStatusUpdate`, e o `currentTime`
 * > continua **avançando**. Ele só é desinstalado no `teardownPlayer()`.
 *
 * Logo, "o `currentTime` avançou N ms depois do `remove()`" é a mesma pergunta
 * que "o som continuou por N ms", sem depender de alto-falante. É um **proxy
 * declarado**, não o som em si: ele prova que o player seguiu rodando. O número
 * no ouvido, no aparelho, continua sendo o critério de aceite do card.
 *
 * As duas variantes são o par que isola a causa:
 *
 * | Variante | O que faz em T0 |
 * |---|---|
 * | `a` | `remove()` só — o código de ANTES do CARD-042 |
 * | `b` | `pause()` e depois `remove()` — a correção que entrou |
 *
 * **Resultado no Simulador (CARD-042):** `a` → 2008–2300 ms de avanço (o resto
 * inteiro do arquivo); `b` → 1–2 ms. O número no aparelho é dívida do card.
 *
 * ```
 * xcrun simctl openurl booted "voicecoach://diagnostico-silencio?variante=a"
 * ```
 *
 * **Armadilha medida:** vindo de fora do app, o deep link abre um diálogo
 * *"Open in Voicecoach?"* que exige um toque, e nesta máquina o `osascript` não
 * tem acesso assistivo para tocá-lo (CARD-011). No Simulador, sem mão na tela,
 * a saída é montar a rota temporariamente em `app/index.tsx`. **No iPhone o
 * problema não existe:** os botões `a` e `b` estão na própria tela.
 */

import { Asset } from 'expo-asset';
import { type AudioPlayer, createAudioPlayer, setAudioModeAsync } from 'expo-audio';
import { useLocalSearchParams } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { alvo, espaco, texto, useCores } from '@/theme/tokens';

const INSUMO = require('../assets/medicao/fala-de-referencia.wav');

/** Quanto se deixa tocar antes de mandar calar. */
const TOCA_ANTES_MS = 500;
/** Por quanto tempo se observa DEPOIS do T0. O insumo tem 2,3 s. */
const OBSERVA_DEPOIS_MS = 3000;

type Amostra = {
  /** ms desde T0 — o instante em que a variante foi aplicada. */
  dt: number;
  /** `currentTime` do player, em segundos. */
  t: number;
  playing: boolean;
};

type Resultado = {
  variante: string;
  /** `currentTime` no instante T0. */
  tNoT0: number;
  /** Quanto o `currentTime` avançou depois do T0, em ms. **O número.** */
  avancoMs: number;
  /** `dt` da última amostra em que o tempo ainda andou. */
  ultimoAvancoEm: number;
  amostras: number;
  /** Quantas amostras depois do T0 ainda vieram com `playing: true`. */
  aindaTocando: number;
};

export default function DiagnosticoSilencio() {
  const cores = useCores();
  const parametros = useLocalSearchParams<{ variante?: string }>();
  const [resultado, setResultado] = useState<Resultado | null>(null);
  const [nota, setNota] = useState('pronta');

  // O player vive num ref pelo mesmo motivo do resto do app: é objeto nativo,
  // não estado do React. Aqui ele tem um papel extra — manter a referência VIVA
  // depois do `remove()` é o que permite continuar ouvindo os eventos dele.
  const player = useRef<AudioPlayer | null>(null);
  const amostras = useRef<Amostra[]>([]);
  const t0 = useRef<number | null>(null);

  const rodar = useCallback(async (variante: string) => {
    setResultado(null);
    amostras.current = [];
    t0.current = null;
    setNota(`variante ${variante}: carregando o insumo`);

    const asset = Asset.fromModule(INSUMO);
    await asset.downloadAsync();
    const uri = asset.localUri ?? asset.uri;

    await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true });

    // `updateInterval: 50` pelo mesmo motivo do ADR-0047 §6: um relógio de
    // 500 ms não julga um critério de 200 ms.
    const p = createAudioPlayer({ uri }, { updateInterval: 50 });
    player.current = p;

    p.addListener('playbackStatusUpdate', (status) => {
      if (t0.current === null) return; // só interessa o DEPOIS
      amostras.current.push({
        dt: Date.now() - t0.current,
        t: status.currentTime,
        playing: status.playing,
      });
    });

    p.play();
    setNota(`variante ${variante}: tocando`);
    await new Promise((r) => setTimeout(r, TOCA_ANTES_MS));

    // ---- T0: o instante em que o aluno tocaria em gravar ----
    const tNoT0 = p.currentTime;
    t0.current = Date.now();
    if (variante === 'b') p.pause();
    p.remove();
    setNota(`variante ${variante}: observando`);

    await new Promise((r) => setTimeout(r, OBSERVA_DEPOIS_MS));

    const colhidas = amostras.current;
    let avanco = 0;
    let ultimoAvancoEm = 0;
    let anterior = tNoT0;
    for (const a of colhidas) {
      if (a.t > anterior + 0.001) {
        avanco = a.t - tNoT0;
        ultimoAvancoEm = a.dt;
        anterior = a.t;
      }
    }

    const fim: Resultado = {
      variante,
      tNoT0,
      avancoMs: Math.round(avanco * 1000),
      ultimoAvancoEm,
      amostras: colhidas.length,
      aindaTocando: colhidas.filter((a) => a.playing).length,
    };
    setResultado(fim);
    setNota('concluída');
    console.info(
      `[diagnostico-silencio] variante=${fim.variante} · t(T0)=${fim.tNoT0.toFixed(3)}s · ` +
        `AVANÇO DEPOIS DO REMOVE = ${fim.avancoMs}ms · último avanço em +${fim.ultimoAvancoEm}ms · ` +
        `${fim.amostras} amostras · ${fim.aindaTocando} com playing=true`,
    );
  }, []);

  useEffect(() => {
    const variante = parametros.variante;
    if (variante === 'a' || variante === 'b') void rodar(variante);
  }, [parametros.variante, rodar]);

  return (
    <SafeAreaView style={[estilos.tela, { backgroundColor: cores.fundo }]}>
      <ScrollView contentContainerStyle={estilos.conteudo}>
        <Text style={[texto.display, { color: cores.tinta }]}>
          Diagnóstico: silêncio
        </Text>
        <Text style={[texto.apoio, { color: cores.secundario }]}>{nota}</Text>

        <View style={estilos.botoes}>
          <Pressable
            accessibilityRole="button"
            style={[estilos.botao, { borderColor: cores.tinta }]}
            onPress={() => void rodar('a')}
          >
            <Text style={[texto.corpo, { color: cores.tinta }]}>a · remove()</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            style={[estilos.botao, { borderColor: cores.tinta }]}
            onPress={() => void rodar('b')}
          >
            <Text style={[texto.corpo, { color: cores.tinta }]}>
              b · pause() + remove()
            </Text>
          </Pressable>
        </View>

        {resultado ? (
          <View style={estilos.resultado}>
            <Text style={[texto.corpo, { color: cores.tinta }]}>
              variante {resultado.variante}
            </Text>
            <Text style={[texto.display, { color: cores.acento }]}>
              {resultado.avancoMs} ms
            </Text>
            <Text style={[texto.apoio, { color: cores.secundario }]}>
              de avanço do currentTime depois do remove()
            </Text>
            <Text style={[texto.apoio, { color: cores.secundario }]}>
              último avanço em +{resultado.ultimoAvancoEm} ms · {resultado.amostras}{' '}
              amostras · {resultado.aindaTocando} com playing=true
            </Text>
          </View>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const estilos = StyleSheet.create({
  tela: {
    flex: 1,
    paddingHorizontal: espaco.lg,
  },
  conteudo: {
    flexGrow: 1,
    justifyContent: 'center',
    gap: espaco.md,
  },
  botoes: {
    gap: espaco.sm,
  },
  botao: {
    minHeight: alvo.minimo,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1,
    borderRadius: espaco.sm,
    paddingHorizontal: espaco.md,
  },
  resultado: {
    gap: espaco.xs,
    alignItems: 'center',
  },
});
