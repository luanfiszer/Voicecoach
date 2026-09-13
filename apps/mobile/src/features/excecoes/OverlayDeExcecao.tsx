/**
 * As quatro telas de exceção (CARD-027, artboards 14/15/16), como o
 * `OverlayPermissao` do artboard 13: um `Modal` transparente, cartão sobre a
 * conversa. Um componente, quatro conteúdos — não quatro componentes — porque
 * os quatro compartilham a mesma forma (título + explicação + até dois
 * botões) e o mesmo insumo (`ConteudoDeExcecao | null`).
 *
 * **"Avisar quando voltar" do artboard 16 (pausado) não está aqui, e não é
 * esquecimento** — é push, cortado pela visão §F, e o CARD-027 registra por
 * quê no próprio card. O botão "Entendi" que a tela de pausado mostra não
 * está em nenhum artboard: sem ele o aluno ficaria sem nenhuma saída depois
 * que o único botão do artboard foi cortado — a alternativa (nenhum botão)
 * trancaria a tela, o que nenhum artboard pede.
 */

import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';

import {
  type ConteudoDeExcecao,
  MENSAGEM_OFFLINE,
  mensagemDeTravamento,
  TITULOS,
} from '@/features/excecoes/conteudoDaExcecao';
import { alvo, espaco, texto, useCores } from '@/theme/tokens';

type Props = {
  conteudo: ConteudoDeExcecao | null;
  /** "Tentar enviar de novo" (offline) — reenvia a mesma gravação. */
  aoTentarDeNovo: () => void;
  /** "Descartar" (travado) — chama o servidor e limpa a tela. */
  aoDescartar: () => void;
  /** "Gravar de novo" (travado) e "Entendi" (cota/pausado) — só fecha. */
  aoFechar: () => void;
};

export function OverlayDeExcecao({
  conteudo,
  aoTentarDeNovo,
  aoDescartar,
  aoFechar,
}: Props) {
  const cores = useCores();

  return (
    <Modal
      visible={conteudo !== null}
      transparent
      animationType="fade"
      onRequestClose={aoFechar}
    >
      <View style={estilos.fundo}>
        <View style={[estilos.cartao, { backgroundColor: cores.fundo }]}>
          {conteudo ? (
            <>
              <Text style={[texto.display, { color: cores.tinta }]}>
                {TITULOS[conteudo.tipo]}
              </Text>
              <Text style={[texto.corpo, { color: cores.secundario }]}>
                {mensagemDe(conteudo)}
              </Text>

              {conteudo.tipo === 'offline' ? (
                <Botao rotulo="Tentar enviar de novo" onPress={aoTentarDeNovo} />
              ) : null}

              {conteudo.tipo === 'travado' ? (
                <View style={estilos.linha}>
                  <Botao rotulo="Gravar de novo" onPress={aoFechar} />
                  <Botao rotulo="Descartar" onPress={aoDescartar} secundario />
                </View>
              ) : null}

              {conteudo.tipo === 'cota' || conteudo.tipo === 'pausado' ? (
                <Botao rotulo="Entendi" onPress={aoFechar} secundario />
              ) : null}
            </>
          ) : null}
        </View>
      </View>
    </Modal>
  );
}

function mensagemDe(conteudo: ConteudoDeExcecao): string {
  switch (conteudo.tipo) {
    case 'offline':
      return MENSAGEM_OFFLINE;
    case 'cota':
    case 'pausado':
      return conteudo.mensagem;
    case 'travado':
      return mensagemDeTravamento(conteudo.segundos);
  }
}

function Botao({
  rotulo,
  onPress,
  secundario = false,
}: {
  rotulo: string;
  onPress: () => void;
  secundario?: boolean;
}) {
  const cores = useCores();
  return (
    <Pressable
      accessibilityRole="button"
      style={[
        estilos.botao,
        secundario
          ? {
              backgroundColor: 'transparent',
              borderWidth: 1,
              borderColor: cores.secundario,
            }
          : { backgroundColor: cores.acento },
      ]}
      onPress={onPress}
    >
      <Text
        style={[
          texto.corpo,
          estilos.rotuloDoBotao,
          { color: secundario ? cores.tinta : cores.sobreAcento },
        ]}
      >
        {rotulo}
      </Text>
    </Pressable>
  );
}

const estilos = StyleSheet.create({
  fundo: {
    flex: 1,
    justifyContent: 'center',
    padding: espaco.lg,
    backgroundColor: 'rgba(0,0,0,0.45)',
  },
  cartao: {
    borderRadius: 28,
    padding: espaco.lg,
    gap: espaco.md,
  },
  linha: {
    flexDirection: 'row',
    gap: espaco.sm,
  },
  botao: {
    flex: 1,
    minHeight: alvo.minimo,
    borderRadius: alvo.minimo / 2,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: espaco.lg,
  },
  rotuloDoBotao: {
    fontWeight: '600',
  },
});
