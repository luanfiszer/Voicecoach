/**
 * Login por e-mail+senha (CARD-050, artboard 11 sem o código de convite —
 * ele morreu com o ADR-0010: app público é o "beta aberto" do gatilho).
 */

import { useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { BotaoPrimario } from '@/features/auth/BotaoPrimario';
import { CampoDeTexto } from '@/features/auth/CampoDeTexto';
import { LinkDeTexto } from '@/features/auth/LinkDeTexto';
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
});
