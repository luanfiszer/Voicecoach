/**
 * A tela de Histórico — artboard 10, a "consulta rápida" do CARD-029.
 *
 * **O que está aqui e o que não está.** Está a listagem com data, duração,
 * turnos e correções, o aviso de áudio expirado (RF3 do CARD-030 chegando à
 * tela pela primeira vez) e o estado vazio. **Não está**: abrir uma sessão e
 * reproduzir a conversa — é a análise completa, e é web (Fase 5); busca ou
 * filtro; qualquer sessão além dos 30 dias que o servidor já corta.
 */

import type { SessaoDoHistorico } from '@voicecoach/api-client';
import { RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import {
  AVISO_DE_AUDIO_EXPIRADO,
  cabecalhoDaSessao,
  formatarDuracao,
  NOTA_DA_JANELA,
  rotuloDeCorrecoes,
  rotuloDeTurnos,
} from '@/features/historico/rotulosDoHistorico';
import { useHistorico } from '@/features/historico/useHistorico';
import { espaco, texto, useCores } from '@/theme/tokens';

function CardDaSessao({ sessao, agora }: { sessao: SessaoDoHistorico; agora: Date }) {
  const cores = useCores();

  return (
    <View style={[estilos.card, { backgroundColor: cores.superficie }]}>
      <View style={estilos.linhaDoTopo}>
        <Text style={[texto.corpo, estilos.negrito, { color: cores.tinta }]}>
          {cabecalhoDaSessao(sessao.started_at, agora)}
        </Text>
        <Text style={[texto.apoio, { color: cores.secundario }]}>
          {formatarDuracao(sessao.spoken_seconds)}
        </Text>
      </View>

      <View style={estilos.chips}>
        <View style={[estilos.chip, { backgroundColor: cores.acentoSuave }]}>
          <Text style={[texto.apoio, estilos.negrito, { color: cores.acento }]}>
            {rotuloDeCorrecoes(sessao.corrections)}
          </Text>
        </View>
        <View style={[estilos.chip, { backgroundColor: cores.chip }]}>
          <Text style={[texto.apoio, { color: cores.secundario }]}>
            {rotuloDeTurnos(sessao.turns)}
          </Text>
        </View>
      </View>

      {sessao.reply_media_available ? null : (
        <Text style={[texto.apoio, estilos.aviso, { color: cores.secundario }]}>
          ⓘ {AVISO_DE_AUDIO_EXPIRADO}
        </Text>
      )}
    </View>
  );
}

export function TelaHistorico() {
  const cores = useCores();
  const { estado, recarregar } = useHistorico();
  // Um só `Date` por render, não um por card: 3–30 sessões lidas contra o
  // MESMO instante, ou "Hoje"/"Ontem" poderiam divergir entre linhas se a
  // lista renderizasse atravessando a virada da meia-noite.
  const agora = new Date();

  return (
    <SafeAreaView style={[estilos.tela, { backgroundColor: cores.fundo }]}>
      <ScrollView
        contentContainerStyle={estilos.conteudo}
        refreshControl={
          <RefreshControl
            refreshing={estado.tipo === 'carregando'}
            onRefresh={recarregar}
          />
        }
      >
        <View style={estilos.cabecalho}>
          <Text style={[texto.display, { color: cores.tinta }]}>Histórico</Text>
          <Text style={[texto.apoio, { color: cores.secundario }]}>
            Consulta rápida. A análise completa fica no app web.
          </Text>
        </View>

        {estado.tipo === 'falhou' ? (
          <Text style={[texto.corpo, { color: cores.secundario }]}>
            {estado.mensagem}
          </Text>
        ) : null}

        {estado.tipo === 'vazio' ? (
          <Text style={[texto.corpo, { color: cores.secundario }]}>
            Nenhuma sessão ainda. Sua primeira conversa aparece aqui.
          </Text>
        ) : null}

        {estado.tipo === 'pronto'
          ? estado.sessoes.map((sessao) => (
              <CardDaSessao key={sessao.id} sessao={sessao} agora={agora} />
            ))
          : null}

        {estado.tipo === 'pronto' ? (
          <Text style={[texto.apoio, estilos.nota, { color: cores.secundario }]}>
            {NOTA_DA_JANELA}
          </Text>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const estilos = StyleSheet.create({
  tela: { flex: 1 },
  conteudo: { padding: espaco.md, gap: espaco.md },
  cabecalho: { gap: espaco.xs },
  card: { borderRadius: 14, padding: espaco.md, gap: espaco.sm },
  linhaDoTopo: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  negrito: { fontWeight: '600' },
  chips: { flexDirection: 'row', gap: espaco.sm },
  chip: {
    paddingHorizontal: espaco.sm,
    paddingVertical: espaco.xs,
    borderRadius: 8,
  },
  aviso: { fontStyle: 'italic' },
  nota: { textAlign: 'center', paddingTop: espaco.sm },
});
