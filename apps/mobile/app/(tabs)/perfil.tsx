/**
 * Perfil (CARD-050 mínimo + delete de conta do CARD-051, ADR-0069).
 *
 * Saldo de cota e outros dados da conta continuam fora daqui — o card só
 * promete "a tela de conta que o CARD-051 completa", e o que o CARD-051
 * completa é justamente a exclusão, exigência de loja (Guideline 5.1.1(v))
 * e de LGPD. O resto (nome, e-mail exibido) fica para quando algum card
 * pedir.
 */

import { criarCliente } from '@voicecoach/api-client';
import { useMemo, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { config } from '@/config';
import { BotaoPrimario } from '@/features/auth/BotaoPrimario';
import { LinkDeTexto } from '@/features/auth/LinkDeTexto';
import { mensagemDeErroDeAuth } from '@/features/auth/mensagensDeErro';
import { useSessao } from '@/features/auth/useSessao';
import { espaco, texto, useCores } from '@/theme/tokens';

export default function Rota() {
  const cores = useCores();
  const sessao = useSessao();
  const cliente = useMemo(
    () => criarCliente({ baseUrl: config.apiBaseUrl, fetch: sessao.fetchAutenticado }),
    [sessao.fetchAutenticado],
  );
  const [confirmando, setConfirmando] = useState(false);
  const [excluindo, setExcluindo] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function excluirConta(): Promise<void> {
    setErro(null);
    setExcluindo(true);
    try {
      await cliente.excluirConta();
      // Do lado do servidor a conta já não aceita mais nada; a limpeza local
      // (storage, estado) é a mesma que o logout faz — não há um segundo
      // caminho para "sessão que acabou de excluir a própria conta".
      await sessao.sair();
    } catch (motivo) {
      setExcluindo(false);
      setErro(mensagemDeErroDeAuth(motivo));
    }
  }

  return (
    <SafeAreaView style={[estilos.tela, { backgroundColor: cores.fundo }]}>
      <ScrollView contentContainerStyle={estilos.conteudo}>
        <Text style={[texto.display, { color: cores.tinta }]}>Perfil</Text>
        <Text style={[texto.apoio, { color: cores.secundario }]}>
          Saldo de cota e dados da conta chegam com um card futuro.
        </Text>
        <View style={estilos.botao}>
          <BotaoPrimario rotulo="Sair" aoTocar={() => void sessao.sair()} />
        </View>

        <View style={estilos.separador} />

        {!confirmando ? (
          <LinkDeTexto
            rotulo="Excluir minha conta"
            aoTocar={() => setConfirmando(true)}
          />
        ) : (
          <View style={estilos.confirmacao}>
            <Text style={[texto.corpo, { color: cores.tinta, fontWeight: '700' }]}>
              Isto não pode ser desfeito
            </Text>
            <Text style={[texto.apoio, { color: cores.secundario }]}>
              Suas gravações, transcrições e correções são apagadas. Você não consegue
              mais entrar com esta conta a partir de agora.
            </Text>
            <Text style={[texto.apoio, { color: cores.secundario }]}>
              Se você tem uma assinatura ativa, excluir a conta{' '}
              <Text style={{ fontWeight: '700' }}>não a cancela</Text> — ela continua
              cobrando. Cancele antes, em Ajustes {'>'} seu nome {'>'} Assinaturas, no
              aparelho onde você assinou.
            </Text>
            {erro !== null ? (
              <Text style={[texto.apoio, { color: cores.perigo }]}>{erro}</Text>
            ) : null}
            <View style={estilos.botao}>
              <BotaoPrimario
                rotulo="Sim, excluir minha conta"
                variante="destrutivo"
                carregando={excluindo}
                aoTocar={() => void excluirConta()}
              />
            </View>
            <LinkDeTexto
              rotulo="Cancelar"
              aoTocar={() => {
                setConfirmando(false);
                setErro(null);
              }}
            />
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const estilos = StyleSheet.create({
  tela: { flex: 1 },
  conteudo: {
    alignItems: 'center',
    gap: espaco.md,
    padding: espaco.lg,
  },
  botao: {
    width: '100%',
    marginTop: espaco.lg,
  },
  separador: {
    height: espaco.lg,
  },
  confirmacao: {
    width: '100%',
    gap: espaco.sm,
    alignItems: 'flex-start',
  },
});
