/**
 * "Confirme seu e-mail" (CARD-050) — sem artboard próprio, derivada do style
 * guide (skill `voicecoach-cliente`: não existe tela desenhada para este
 * estado, e inventar decoração além do necessário seria overengineering).
 *
 * O aluno não faz nada aqui além de esperar e, se quiser, pedir de novo — a
 * confirmação de verdade acontece no clique do link, fora do app
 * (`GET /v1/auth/confirm-email`, CARD-049).
 */

import { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { BotaoPrimario } from '@/features/auth/BotaoPrimario';
import { LinkDeTexto } from '@/features/auth/LinkDeTexto';
import { mensagemDeErroDeAuth } from '@/features/auth/mensagensDeErro';
import { useSessao } from '@/features/auth/useSessao';
import { espaco, texto, useCores } from '@/theme/tokens';

type Props = {
  email: string;
  aoVoltarParaEntrada: () => void;
};

export function TelaConfirmeSeuEmail({ email, aoVoltarParaEntrada }: Props) {
  const cores = useCores();
  const sessao = useSessao();
  const [carregando, setCarregando] = useState(false);
  const [mensagem, setMensagem] = useState<string | null>(null);

  const reenviar = async () => {
    setCarregando(true);
    setMensagem(null);
    try {
      await sessao.reenviarConfirmacao(email);
      setMensagem('Link reenviado. Confira sua caixa de entrada.');
    } catch (falha) {
      setMensagem(mensagemDeErroDeAuth(falha));
    } finally {
      setCarregando(false);
    }
  };

  return (
    <SafeAreaView style={[estilos.tela, { backgroundColor: cores.fundo }]}>
      <View style={estilos.conteudo}>
        <Text style={[texto.display, { color: cores.tinta }]}>Confirme seu e-mail</Text>
        <Text style={[texto.apoio, { color: cores.secundario }]}>
          Enviamos um link de confirmação para{'\n'}
          <Text style={{ color: cores.tinta, fontWeight: '600' }}>{email}</Text>. Toque
          nele para poder começar a falar.
        </Text>

        {mensagem ? (
          <Text style={[texto.apoio, { color: cores.secundario }]}>{mensagem}</Text>
        ) : null}

        <BotaoPrimario
          rotulo="Reenviar e-mail"
          aoTocar={() => void reenviar()}
          carregando={carregando}
        />

        <LinkDeTexto rotulo="Voltar para o login" aoTocar={aoVoltarParaEntrada} />
      </View>
    </SafeAreaView>
  );
}

const estilos = StyleSheet.create({
  tela: { flex: 1 },
  conteudo: {
    flex: 1,
    justifyContent: 'center',
    padding: espaco.lg,
    gap: espaco.md,
  },
});
