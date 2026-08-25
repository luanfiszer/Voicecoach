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

import { BotaoGravar } from '@/features/gravacao/BotaoGravar';
import { OverlayPermissao } from '@/features/gravacao/OverlayPermissao';
import { PlayerLocal } from '@/features/gravacao/PlayerLocal';
import { useGravacao } from '@/features/gravacao/useGravacao';
import { ListaDoTurno } from '@/features/turno/ListaDoTurno';
import { type EstadoDoTurn, useTurno } from '@/features/turno/useTurno';
import { alvo, espaco, texto, useCores } from '@/theme/tokens';

export function TelaConversa() {
  const cores = useCores();
  const gravacao = useGravacao();
  const turno = useTurno();
  const [overlayDispensado, setOverlayDispensado] = useState(false);

  const precisaDeAjustes =
    gravacao.permissao === 'negada-permanentemente' && !overlayDispensado;

  return (
    <SafeAreaView style={[estilos.tela, { backgroundColor: cores.fundo }]}>
      <View style={estilos.cabecalho}>
        <Text style={[texto.display, { color: cores.tinta }]}>Sessão de hoje</Text>
        <Text style={[texto.apoio, { color: cores.secundario }]}>
          {subtitulo(gravacao.estado === 'gravando', turno.estado)}
        </Text>
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
            onPress={gravacao.descartar}
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
    </SafeAreaView>
  );
}

/**
 * O subtítulo do cabeçalho — **a etapa da cascata, não a do desenho antigo**.
 *
 * Os artboards 03–06 descrevem uma sequência anterior à cascata (transcrevendo →
 * pensando → texto → áudio). Hoje o áudio começa antes de o texto do feedback
 * fechar (ADR-0022/0023), e o vocabulário aqui reflete a ordem real.
 */
function subtitulo(gravando: boolean, turno: EstadoDoTurn): string {
  if (gravando) return 'Gravando…';
  switch (turno) {
    case 'ocioso':
      return 'Nenhum turno ainda';
    case 'enviando':
      return 'Enviando…';
    case 'transcrevendo':
      return 'Transcrevendo…';
    case 'ouvindo':
      return 'O professor está falando…';
    case 'concluido':
      return 'Sua vez';
    case 'falhou':
      return 'Algo deu errado';
  }
}

function rotulo(estado: 'ocioso' | 'gravando' | 'gravado'): string {
  switch (estado) {
    case 'ocioso':
      return 'Toque para falar';
    case 'gravando':
      return 'Toque para parar';
    // O rótulo descreve o BOTÃO, não o player: no estado `gravado` o botão
    // grava de novo. "Ouça o que você falou" ficava embaixo dele e sugeria
    // que tocá-lo reproduziria o áudio.
    case 'gravado':
      return 'Toque para gravar de novo';
  }
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
