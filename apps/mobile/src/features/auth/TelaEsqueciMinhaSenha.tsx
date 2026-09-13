/**
 * "Esqueci minha senha" — pedido do link de redefinição (CARD-050).
 *
 * **A resposta é sempre a mesma**, e-mail cadastrado ou não (CARD-049: não
 * vazar quais e-mails existem). A tela não pode dizer "e-mail não encontrado"
 * mesmo que quisesse — o servidor nunca conta essa diferença.
 */

import { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { BotaoPrimario } from '@/features/auth/BotaoPrimario';
import { CampoDeTexto } from '@/features/auth/CampoDeTexto';
import { LinkDeTexto } from '@/features/auth/LinkDeTexto';
import { mensagemDeErroDeAuth } from '@/features/auth/mensagensDeErro';
import { useSessao } from '@/features/auth/useSessao';
import { espaco, texto, useCores } from '@/theme/tokens';

type Props = {
  aoJaTerOCodigo: () => void;
  aoVoltarParaEntrada: () => void;
};

export function TelaEsqueciMinhaSenha({ aoJaTerOCodigo, aoVoltarParaEntrada }: Props) {
  const cores = useCores();
  const sessao = useSessao();
  const [email, setEmail] = useState('');
  const [carregando, setCarregando] = useState(false);
  const [enviado, setEnviado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const pedir = async () => {
    setErro(null);
    setCarregando(true);
    try {
      await sessao.pedirRedefinicaoDeSenha(email.trim());
      setEnviado(true);
    } catch (falha) {
      setErro(mensagemDeErroDeAuth(falha));
    } finally {
      setCarregando(false);
    }
  };

  return (
    <SafeAreaView style={[estilos.tela, { backgroundColor: cores.fundo }]}>
      <View style={estilos.conteudo}>
        <Text style={[texto.display, { color: cores.tinta }]}>Esqueceu sua senha?</Text>
        <Text style={[texto.apoio, { color: cores.secundario }]}>
          Informe seu e-mail. Se ele tiver conta, enviamos um link para redefinir a
          senha.
        </Text>

        <CampoDeTexto
          rotulo="E-mail"
          valor={email}
          aoMudar={setEmail}
          tipoDeTeclado="email-address"
        />

        {erro ? (
          <Text style={[texto.apoio, { color: cores.acento }]}>{erro}</Text>
        ) : null}
        {enviado ? (
          <Text style={[texto.apoio, { color: cores.secundario }]}>
            Se esse e-mail tiver conta, o link chegou. Volte aqui com o código assim que
            o tiver.
          </Text>
        ) : null}

        <BotaoPrimario
          rotulo="Enviar link"
          aoTocar={() => void pedir()}
          carregando={carregando}
          desabilitado={email.trim().length === 0}
        />

        <LinkDeTexto rotulo="Já tenho o código" aoTocar={aoJaTerOCodigo} />
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
