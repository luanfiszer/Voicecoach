/**
 * A máquina de estados da gravação, fora do componente.
 *
 * Duas coisas aqui não têm paralelo no React web e são o ponto de aprendizado
 * do CARD-011:
 *
 * 1. **A permissão é estado da PLATAFORMA, não do app.** Ela sobrevive ao
 *    processo, é o usuário quem a muda (nos Ajustes do sistema), e por isso ela
 *    é sempre CONSULTADA, nunca guardada como verdade. Daí os três estados —
 *    e o terceiro (`negada-permanentemente`) existe porque no iOS, depois da
 *    primeira negação, `requestRecordingPermissionsAsync()` volta negado NA
 *    HORA, sem mostrar diálogo nenhum. O único caminho é `Linking.openSettings()`.
 * 2. **O recorder é um objeto nativo com vida própria.** `recorder.record()`
 *    não é `setState`: quem sabe se está gravando e há quanto tempo é o lado
 *    nativo, e `useAudioRecorderState` faz polling dele num intervalo. É por
 *    isso que o limite de duração se aplica reagindo a `durationMillis`, e não
 *    com um `setTimeout` — o `setTimeout` mediria o tempo do JavaScript, que
 *    não é o tempo do microfone.
 */

import {
  getRecordingPermissionsAsync,
  RecordingPresets,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  useAudioRecorder,
  useAudioRecorderState,
} from 'expo-audio';
import { useCallback, useEffect, useState } from 'react';

import { config } from '@/config';

/** Os três estados de permissão (o terceiro é o que o artboard 13 resolve). */
export type Permissao = 'indefinida' | 'concedida' | 'negada-permanentemente';

/** O estado visível da tela. */
export type EstadoGravacao = 'ocioso' | 'gravando' | 'gravado';

export type Gravacao = {
  permissao: Permissao;
  estado: EstadoGravacao;
  /** Segundos decorridos, vindos do lado nativo — não do JavaScript. */
  decorridos: number;
  /** Limite em segundos, de `app.json > extra` (menor que o do servidor). */
  limite: number;
  /** dBFS do microfone (negativo, 0 = saturado). `null` até o primeiro sample. */
  nivel: number | null;
  /** Verdadeiro quando a gravação parou sozinha por ter batido o limite. */
  pararaPorLimite: boolean;
  /** URI local do arquivo gravado, quando existe. */
  uri: string | null;
  iniciar: () => Promise<void>;
  parar: () => Promise<void>;
  descartar: () => void;
};

const OPCOES = { ...RecordingPresets.HIGH_QUALITY, isMeteringEnabled: true };

/** Traduz o `PermissionResponse` do Expo para os três estados do produto. */
function classificar(resposta: { granted: boolean; canAskAgain: boolean }): Permissao {
  if (resposta.granted) return 'concedida';
  return resposta.canAskAgain ? 'indefinida' : 'negada-permanentemente';
}

export function useGravacao(): Gravacao {
  const recorder = useAudioRecorder(OPCOES);
  // 100 ms: o limite de duração precisa morder com precisão visível, e o
  // default de 500 ms deixaria o contador andando aos meios-segundos.
  const estadoNativo = useAudioRecorderState(recorder, 100);

  const [permissao, setPermissao] = useState<Permissao>('indefinida');
  const [uri, setUri] = useState<string | null>(null);
  const [pararaPorLimite, setPararaPorLimite] = useState(false);

  // Consulta a permissão no arranque. CONSULTA, não pede: pedir sem que o
  // aluno tenha tocado em nada gasta a única chance de diálogo que o iOS dá.
  useEffect(() => {
    void getRecordingPermissionsAsync().then((r) => setPermissao(classificar(r)));
  }, []);

  const pararInterno = useCallback(async () => {
    await recorder.stop();
    setUri(recorder.uri ?? null);
    // No iOS, o modo de áudio que permite gravar joga o playback para o
    // alto-falante do ouvido, baixinho. Desligar `allowsRecording` ao terminar
    // é o que faz o "ouvir o que gravei" sair no alto-falante de verdade.
    await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true });
  }, [recorder]);

  const iniciar = useCallback(async () => {
    const atual = await getRecordingPermissionsAsync();
    let situacao = classificar(atual);

    if (situacao === 'indefinida') {
      situacao = classificar(await requestRecordingPermissionsAsync());
    }
    setPermissao(situacao);
    if (situacao !== 'concedida') return;

    setUri(null);
    setPararaPorLimite(false);
    await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
    await recorder.prepareToRecordAsync();
    recorder.record();
  }, [recorder]);

  const parar = useCallback(async () => {
    if (!estadoNativo.isRecording) return;
    await pararInterno();
  }, [estadoNativo.isRecording, pararInterno]);

  // O limite de duração. Reage ao relógio do microfone, e o critério de aceite
  // é "para sozinha E INFORMA" — daí o `pararaPorLimite`, que a tela mostra.
  useEffect(() => {
    if (!estadoNativo.isRecording) return;
    if (estadoNativo.durationMillis < config.limiteGravacaoSegundos * 1000) return;
    setPararaPorLimite(true);
    void pararInterno();
  }, [estadoNativo.isRecording, estadoNativo.durationMillis, pararInterno]);

  const descartar = useCallback(() => {
    setUri(null);
    setPararaPorLimite(false);
  }, []);

  const estado: EstadoGravacao = estadoNativo.isRecording
    ? 'gravando'
    : uri
      ? 'gravado'
      : 'ocioso';

  return {
    permissao,
    estado,
    decorridos: estadoNativo.durationMillis / 1000,
    limite: config.limiteGravacaoSegundos,
    nivel: estadoNativo.metering ?? null,
    pararaPorLimite,
    uri,
    iniciar,
    parar,
    descartar,
  };
}
