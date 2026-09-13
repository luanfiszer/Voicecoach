/**
 * A tela de conversa — o artboard 01, no que este card entrega.
 *
 * O que está aqui e o que NÃO está, de propósito:
 * - **Está:** os três estados de gravação, o ciclo de permissão inteiro, o
 *   limite de duração que para sozinha e informa, e ouvir o que foi gravado.
 * - **Não está:** o histórico de turns do artboard 01 (bolha do aluno, resposta
 *   do professor, card de correção). Isso é CARD-012/CARD-016 — e a ORDEM em
 *   que aquilo aparece está invertida no design: com a cascata (ADR-0022/0023)
 *   o áudio vem primeiro, em trechos, e o texto do feedback fecha depois.
 *   Montar a lista agora, na ordem desenhada, seria construir errado de origem.
 * - **Não está, e não é esquecimento:** `reiniciar demo` / `a. idle` do rodapé
 *   do artboard 01 são andaime de apresentação (premissa P2 de
 *   `docs/reconciliacao-telas-dominio.md`, registrada lá como não confirmada).
 *
 * Nota de React Native, para quem vem do React web: não existe texto solto.
 * Toda string tem de estar dentro de `<Text>` — `<View>` é uma caixa e não
 * renderiza caracteres. E `StyleSheet` não é CSS: não há cascata, não há
 * herança (a cor do `<Text>` filho não vem do pai) e não há unidade — os
 * números são pontos independentes de densidade de tela.
 */

import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { OverlayDeExcecao } from '@/features/excecoes/OverlayDeExcecao';
import { BotaoGravar } from '@/features/gravacao/BotaoGravar';
import { OverlayPermissao } from '@/features/gravacao/OverlayPermissao';
import { PlayerLocal } from '@/features/gravacao/PlayerLocal';
import { rotulo, subtitulo } from '@/features/gravacao/rotulos';
import { useGravacao } from '@/features/gravacao/useGravacao';
import { ListaDoTurno } from '@/features/turno/ListaDoTurno';
import { formatarResumo } from '@/features/turno/rotulosDeCorrecao';
import { useTurno } from '@/features/turno/useTurno';
import { alvo, espaco, texto, useCores } from '@/theme/tokens';

export function TelaConversa() {
  const cores = useCores();
  const gravacao = useGravacao();
  const turno = useTurno();
  const [overlayDispensado, setOverlayDispensado] = useState(false);

  const precisaDeAjustes =
    gravacao.permissao === 'negada-permanentemente' && !overlayDispensado;
  // Fundação do resumo pós-sessão da Fase 6 (CARD-016): `null` enquanto
  // nenhuma correção aconteceu ainda — sem linha de "0 correções" poluindo
  // uma sessão que só teve acertos.
  const resumo = formatarResumo(turno.resumo);

  return (
    <SafeAreaView style={[estilos.tela, { backgroundColor: cores.fundo }]}>
      <View style={estilos.cabecalho}>
        <Text style={[texto.display, { color: cores.tinta }]}>Sessão de hoje</Text>
        <Text style={[texto.apoio, { color: cores.secundario }]}>
          {subtitulo(gravacao.estado === 'gravando', turno.estado)}
        </Text>
        {resumo ? (
          <Text style={[texto.apoio, { color: cores.secundario }]}>{resumo}</Text>
        ) : null}
      </View>

      <ScrollView style={estilos.centro} contentContainerStyle={estilos.conteudo}>
        {gravacao.uri ? <PlayerLocal key={gravacao.uri} uri={gravacao.uri} /> : null}

        <ListaDoTurno turno={turno} />

        {gravacao.pararaPorLimite ? (
          <Text style={[texto.apoio, estilos.aviso, { color: cores.acento }]}>
            Chegamos ao limite de {gravacao.limite}s — sua fala foi guardada até aqui.
          </Text>
        ) : null}
      </ScrollView>

      <View style={estilos.rodape}>
        {gravacao.estado === 'gravando' ? (
          <Text style={[texto.apoio, { color: cores.secundario }]}>
            {formatar(gravacao.decorridos)} / {formatar(gravacao.limite)}
          </Text>
        ) : null}

        <BotaoGravar
          gravando={gravacao.estado === 'gravando'}
          nivel={gravacao.nivel}
          aoTocar={() => {
            setOverlayDispensado(false);
            if (gravacao.estado === 'gravando') {
              // O marco 1 é o instante em que `stop()` retorna — o dedo saiu do
              // botão. Ele é capturado AQUI e viaja junto, para que o upload não
              // comece a contar de um relógio diferente do da gravação.
              void gravacao.parar().then((uri) => {
                if (uri) void turno.enviar(uri, Date.now());
              });
              return;
            }
            // **A ordem é invariante, não coincidência de escrita** (CARD-042).
            // `limpar()` é SÍNCRONO e cala o professor antes de qualquer outra
            // coisa acontecer; `iniciar()` é assíncrono — pede permissão e troca
            // a categoria da sessão de áudio do iOS. Invertê-los deixaria o
            // professor falando durante todo o `await`, e em modo avião ou com
            // o diálogo de permissão aberto isso é tempo indeterminado.
            // Silenciar é operação local: nada aqui pode esperar por rede.
            turno.limpar();
            void gravacao.iniciar();
          }}
        />

        <Text style={[texto.corpo, { color: cores.tinta }]}>
          {rotulo(gravacao.estado)}
        </Text>

        {gravacao.estado === 'gravado' ? (
          <Pressable
            accessibilityRole="button"
            style={estilos.regravar}
            onPress={() => {
              // **"Regravar" é recomeçar, e recomeçar cala o professor**
              // (CARD-042). Antes, este link só descartava a gravação local:
              // o turn já tinha sido enviado ao parar de gravar, e a resposta
              // dele seguia tocando por cima da tentativa nova — é muito
              // provavelmente o gesto da queixa original do card. Mesma
              // invariante do botão acima: silêncio síncrono primeiro. O turn
              // continua no servidor até o CARD-043.
              turno.limpar();
              gravacao.descartar();
            }}
          >
            <Text
              style={[texto.apoio, estilos.sublinhado, { color: cores.secundario }]}
            >
              regravar
            </Text>
          </Pressable>
        ) : null}
      </View>

      <OverlayPermissao
        visivel={precisaDeAjustes}
        aoFechar={() => setOverlayDispensado(true)}
      />

      <OverlayDeExcecao
        conteudo={turno.excecao}
        aoTentarDeNovo={turno.tentarNovamente}
        aoDescartar={() => void turno.descartar()}
        aoFechar={turno.limpar}
      />
    </SafeAreaView>
  );
}

function formatar(segundos: number): string {
  const total = Math.floor(segundos);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
}

const estilos = StyleSheet.create({
  tela: {
    flex: 1,
    paddingHorizontal: espaco.lg,
  },
  cabecalho: {
    paddingTop: espaco.md,
    gap: espaco.xs,
  },
  centro: {
    flex: 1,
  },
  conteudo: {
    flexGrow: 1,
    justifyContent: 'center',
    gap: espaco.md,
    paddingVertical: espaco.md,
  },
  aviso: {
    textAlign: 'center',
  },
  rodape: {
    alignItems: 'center',
    paddingBottom: espaco.lg,
    gap: espaco.sm,
  },
  regravar: {
    minHeight: alvo.minimo,
    justifyContent: 'center',
    paddingHorizontal: espaco.md,
  },
  sublinhado: {
    textDecorationLine: 'underline',
  },
});
