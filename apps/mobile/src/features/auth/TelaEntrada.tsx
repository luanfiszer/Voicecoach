/**
 * Login por e-mail+senha (CARD-050, artboard 11 sem o código de convite —
 * ele morreu com o ADR-0010: app público é o "beta aberto" do gatilho).
 */

import { Ionicons } from '@expo/vector-icons';
import { useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { BotaoPrimario } from '@/features/auth/BotaoPrimario';
import { CampoDeTexto } from '@/features/auth/CampoDeTexto';
import {
  LoginGoogleCancelado,
  obterIdTokenDoGoogle,
} from '@/features/auth/googleSignIn';
import { LinkDeTexto } from '@/features/auth/LinkDeTexto';
import { LogoGoogle } from '@/features/auth/LogoGoogle';
import { mensagemDeErroDeAuth } from '@/features/auth/mensagensDeErro';
import { useSessao } from '@/features/auth/useSessao';
import { espaco, texto, useCores } from '@/theme/tokens';

type Props = {
  aoIrParaCadastro: () => void;
  aoIrParaEsqueciSenha: () => void;
};

export function TelaEntrada({ aoIrParaCadastro, aoIrParaEsqueciSenha }: Props) {
  const cores = useCores();
  const sessao = useSessao();
  const [email, setEmail] = useState('');
  const [senha, setSenha] = useState('');
  const [carregando, setCarregando] = useState(false);
  const [carregandoGoogle, setCarregandoGoogle] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const entrar = async () => {
    setErro(null);
    setCarregando(true);
    try {
      await sessao.login(email.trim(), senha);
      // Sucesso: `estado` muda para `autenticado` e o layout raiz troca de
      // tela sozinho — nenhuma navegação explícita é necessária aqui.
    } catch (falha) {
      setErro(mensagemDeErroDeAuth(falha));
    } finally {
      setCarregando(false);
    }
  };

  const entrarComGoogle = async () => {
    setErro(null);
    setCarregandoGoogle(true);
    try {
      const idToken = await obterIdTokenDoGoogle();
      await sessao.loginGoogle(idToken);
    } catch (falha) {
      // Cancelamento não é erro — o aluno só voltou para a tela.
      if (!(falha instanceof LoginGoogleCancelado)) {
        setErro(mensagemDeErroDeAuth(falha));
      }
    } finally {
      setCarregandoGoogle(false);
    }
  };

  return (
    <SafeAreaView style={[estilos.tela, { backgroundColor: cores.fundo }]}>
      <ScrollView
        contentContainerStyle={estilos.conteudo}
        keyboardShouldPersistTaps="handled"
      >
        <Text style={[texto.display, { color: cores.tinta }]}>Bem-vindo de volta</Text>
        <Text style={[texto.apoio, { color: cores.secundario }]}>
          Entre para continuar de onde parou.
        </Text>

        <View style={estilos.campos}>
          <CampoDeTexto
            rotulo="E-mail"
            valor={email}
            aoMudar={setEmail}
            tipoDeTeclado="email-address"
          />
          <CampoDeTexto rotulo="Senha" valor={senha} aoMudar={setSenha} senha />
        </View>

        {erro ? (
          <Text style={[texto.apoio, estilos.erro, { color: cores.acento }]}>
            {erro}
          </Text>
        ) : null}

        <BotaoPrimario
          rotulo="Entrar"
          aoTocar={() => void entrar()}
          carregando={carregando}
          desabilitado={email.trim().length === 0 || senha.length === 0}
        />

        <LinkDeTexto rotulo="Esqueci minha senha" aoTocar={aoIrParaEsqueciSenha} />

        <View style={estilos.separador}>
          <View style={[estilos.linha, { backgroundColor: cores.chip }]} />
          <Text style={[texto.apoio, { color: cores.secundario }]}>ou</Text>
          <View style={[estilos.linha, { backgroundColor: cores.chip }]} />
        </View>

        <BotaoPrimario
          rotulo="Continuar com o Google"
          variante="secundario"
          icone={<LogoGoogle tamanho={18} />}
          carregando={carregandoGoogle}
          aoTocar={() => void entrarComGoogle()}
        />
        <BotaoPrimario
          rotulo="Continuar com a Apple (em breve)"
          variante="secundario"
          icone={<Ionicons name="logo-apple" size={18} color={cores.tinta} />}
          desabilitado
          aoTocar={() => {}}
        />

        <View style={estilos.rodape}>
          <Text style={[texto.apoio, { color: cores.secundario }]}>Não tem conta?</Text>
          <LinkDeTexto rotulo="Criar conta" aoTocar={aoIrParaCadastro} />
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const estilos = StyleSheet.create({
  tela: { flex: 1 },
  conteudo: {
    flexGrow: 1,
    justifyContent: 'center',
    padding: espaco.lg,
    gap: espaco.md,
  },
  campos: {
    gap: espaco.md,
  },
  erro: {
    marginTop: -espaco.xs,
  },
  rodape: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: espaco.xs,
    marginTop: espaco.sm,
  },
  separador: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: espaco.sm,
    marginVertical: espaco.xs,
  },
  linha: {
    flex: 1,
    height: 1,
  },
});
