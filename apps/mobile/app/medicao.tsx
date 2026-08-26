/**
 * A rota de medição — o critério de saída da Fase 1, repetível sem toque.
 *
 * **Por que ela existe.** `p50` implica repetição: uma execução não tem mediana.
 * Nesta máquina o agente **não consegue tocar na tela** (o `osascript` está sem
 * acesso assistivo, conferido no CARD-011), então uma rota que dispara o ciclo
 * inteiro sozinha ao receber um parâmetro de deep link é o que torna N ≥ 10
 * possível:
 *
 * ```
 * xcrun simctl openurl booted "exp://127.0.0.1:8081/--/medicao?execucoes=10&auto=1"
 * ```
 *
 * **O que ela mede, e o que ela NÃO mede — declarado, não subentendido.** O
 * insumo é um WAV fixo empacotado (o mesmo `amazing-project.wav` das medições
 * §§2–10 de `docs/medicao-latencia.md`), e não o microfone. Isso é deliberado:
 * insumo constante é o que torna as N execuções comparáveis entre si e isola o
 * que este card veio medir — upload, fila, transporte, download, decodificação e
 * início do playback. **O custo de parar a gravação fica de fora**, e por isso o
 * marco 1 aqui é *"o envio começou"*, não *"o dedo saiu do botão"*. O número com
 * o microfone real sai da tela de conversa, que mostra os mesmos quatro marcos.
 */

import { Asset } from 'expo-asset';
import { useLocalSearchParams } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { formatar, intervalos, p50 } from '@/features/turno/marcos';
import { useTurno } from '@/features/turno/useTurno';
import { alvo, espaco, texto, useCores } from '@/theme/tokens';

const INSUMO = require('../assets/medicao/fala-de-referencia.wav');

type Rodada = {
  n: number;
  upload: number | null;
  ateOChunk: number | null;
  ateOAudio: number | null;
  total: number | null;
  gaps: number[];
  trechos: number;
  via: string;
  desfecho: string;
  erro: string | null;
};

export default function Medicao() {
  const cores = useCores();
  const parametros = useLocalSearchParams<{ execucoes?: string; auto?: string }>();
  const turno = useTurno();

  const [rodadas, setRodadas] = useState<Rodada[]>([]);
  const [rodando, setRodando] = useState(false);
  const [nota, setNota] = useState<string>('pronta');

  const alvoDeRodadas = useRef(0);
  const emCurso = useRef(false);
  const uri = useRef<string | null>(null);

  const carregarInsumo = useCallback(async (): Promise<string> => {
    if (uri.current) return uri.current;
    // `Asset.fromModule` pega o que o `require` devolveu (um id de asset do
    // bundler, não um caminho) e `downloadAsync` garante que ele existe no
    // sistema de arquivos do APARELHO. Sem paralelo na web: lá o arquivo já é
    // uma URL; aqui ele precisa ser materializado antes de existir como bytes.
    const asset = Asset.fromModule(INSUMO);
    await asset.downloadAsync();
    const local = asset.localUri ?? asset.uri;
    uri.current = local;
    return local;
  }, []);

  const dispararUma = useCallback(async () => {
    const local = await carregarInsumo();
    emCurso.current = true;
    await turno.enviar(local, Date.now());
  }, [carregarInsumo, turno]);

  const comecar = useCallback(
    async (quantas: number) => {
      setRodadas([]);
      alvoDeRodadas.current = quantas;
      setRodando(true);
      setNota(`rodando 1/${quantas}`);
      await dispararUma();
    },
    [dispararUma],
  );

  // Cada rodada fecha quando o turn termina; a seguinte começa aí. Encadear por
  // efeito, e não por laço, é o que respeita o ciclo de vida do React — um `for`
  // com `await` dentro do componente não veria as atualizações de estado.
  useEffect(() => {
    if (!emCurso.current) return;
    if (turno.estado !== 'concluido' && turno.estado !== 'falhou') return;
    // **A rodada só fecha quando o áudio TERMINOU**, não quando o turn
    // completou: o `completed` chega enquanto o primeiro trecho ainda toca, e
    // fechar ali registraria zero gaps com dois trechos — foi o que aconteceu
    // na primeira execução desta rota.
    if (turno.estado === 'concluido' && turno.tocados.length < turno.trechos.length) {
      return;
    }
    emCurso.current = false;

    const i = intervalos(turno.marcos);
    setRodadas((atual) => {
      const proximas = [
        ...atual,
        {
          n: atual.length + 1,
          upload: i.upload,
          ateOChunk: i.ateOChunk,
          ateOAudio: i.ateOAudio,
          total: i.total,
          gaps: turno.gaps,
          trechos: turno.trechos.length,
          via: turno.via ?? '—',
          desfecho: turno.estado,
          erro: turno.erro,
        },
      ];

      if (proximas.length < alvoDeRodadas.current) {
        setNota(`rodando ${proximas.length + 1}/${alvoDeRodadas.current}`);
        // Espera o áudio terminar antes da próxima: medir com o alto-falante
        // ocupado mediria contenção, não latência.
        setTimeout(() => void dispararUma(), 1500);
      } else {
        setRodando(false);
        setNota(`${proximas.length} execuções concluídas`);
      }
      return proximas;
    });
  }, [
    turno.estado,
    turno.marcos,
    turno.gaps,
    turno.trechos,
    turno.via,
    turno.erro,
    turno.tocados,
    dispararUma,
  ]);

  // Disparo por deep link — o que torna a métrica repetível sem ninguém tocar.
  useEffect(() => {
    if (parametros.auto !== '1' || rodadas.length > 0 || rodando) return;
    const quantas = Number.parseInt(parametros.execucoes ?? '10', 10);
    void comecar(Number.isFinite(quantas) && quantas > 0 ? quantas : 10);
  }, [parametros.auto, parametros.execucoes, comecar, rodadas.length, rodando]);

  const totais = rodadas.map((r) => r.total).filter((v): v is number => v !== null);
  const gapsTodos = rodadas.flatMap((r) => r.gaps);

  return (
    <SafeAreaView style={[estilos.tela, { backgroundColor: cores.fundo }]}>
      <Text style={[texto.display, { color: cores.tinta }]}>Medição</Text>
      <Text style={[texto.apoio, { color: cores.secundario }]}>
        {nota} · {turno.estado} · {turno.via ?? '—'}
      </Text>

      <View style={estilos.botoes}>
        {[1, 10].map((quantas) => (
          <Pressable
            key={quantas}
            disabled={rodando}
            style={[estilos.botao, { backgroundColor: cores.acento }]}
            onPress={() => void comecar(quantas)}
          >
            <Text style={[estilos.rotulo, { color: cores.sobreAcento }]}>
              rodar {quantas}×
            </Text>
          </Pressable>
        ))}
      </View>

      <View style={[estilos.resumo, { backgroundColor: cores.superficie }]}>
        <Text style={[texto.rotulo, { color: cores.secundario }]}>
          p50 ATÉ O PRIMEIRO ÁUDIO AUDÍVEL (n={totais.length})
        </Text>
        <Text style={[texto.display, { color: cores.acento }]}>
          {formatar(p50(totais))}
        </Text>
        <Text style={[texto.apoio, { color: cores.secundario }]}>
          gap entre trechos: p50 {formatar(p50(gapsTodos))} · pior{' '}
          {formatar(gapsTodos.length ? Math.max(...gapsTodos) : null)} · n=
          {gapsTodos.length}
        </Text>
      </View>

      <ScrollView style={estilos.tabela}>
        {rodadas.map((r) => (
          <Text key={r.n} style={[texto.apoio, { color: cores.tinta }]}>
            {`#${r.n} ${r.desfecho} ${r.via} · up ${formatar(r.upload)} · chunk ${formatar(
              r.ateOChunk,
            )} · áudio ${formatar(r.ateOAudio)} · TOTAL ${formatar(r.total)} · ${
              r.trechos
            } trechos · gaps [${r.gaps.map((g) => `${g}ms`).join(', ')}]${
              r.erro ? `\n     ERRO: ${r.erro}` : ''
            }`}
          </Text>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

const estilos = StyleSheet.create({
  tela: { flex: 1, padding: espaco.md, gap: espaco.sm },
  botoes: { flexDirection: 'row', gap: espaco.sm },
  botao: {
    flex: 1,
    minHeight: alvo.minimo,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  rotulo: { fontWeight: '600' },
  resumo: { borderRadius: 14, padding: espaco.md, gap: espaco.xs },
  tabela: { flex: 1 },
});
