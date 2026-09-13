/**
 * Cadastro por e-mail+senha (CARD-050, artboard 11 sem o código de convite).
 *
 * **Sucesso não loga o aluno.** O servidor exige e-mail confirmado antes do
 * primeiro turn (ADR-0007) — a resposta certa a um cadastro bem-sucedido é a
 * tela de confirmação, não a sessão autenticada.
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

// Mesmo piso do schema do servidor (`RegisterRequest`, CARD-049) — validar
// aqui só evita a viagem de rede para um erro que o servidor já recusaria.
const SENHA_MINIMA = 8;

type Props = {
  aoRegistrar: (email: string) => void;
  aoIrParaEntrada: () => void;
};

export function TelaCadastro({ aoRegistrar, aoIrParaEntrada }: Props) {
  const cores = useCores();
  const sessao = useSessao();
  const [email, setEmail] = useState('');
  const [senha, setSenha] = useState('');
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const registrar = async () => {
    setErro(null);
    setCarregando(true);
    try {
      await sessao.registrar(email.trim(), senha);
      aoRegistrar(email.trim());
    } catch (falha) {
      setErro(mensagemDeErroDeAuth(falha));
    } finally {
      setCarregando(false);
    }
  };

  const senhaCurta = senha.length > 0 && senha.length < SENHA_MINIMA;

  return (
    <SafeAreaView style={[estilos.tela, { backgroundColor: cores.fundo }]}>
      <ScrollView
        contentContainerStyle={estilos.conteudo}
        keyboardShouldPersistTaps="handled"
      >
        <Text style={[texto.display, { color: cores.tinta }]}>
          Seu tutor de inglês por conversa.
        </Text>
        <Text style={[texto.apoio, { color: cores.secundario }]}>
          Crie sua conta para começar a falar.
        </Text>

        <View style={estilos.campos}>
          <CampoDeTexto
            rotulo="E-mail"
            valor={email}
            aoMudar={setEmail}
            tipoDeTeclado="email-address"
          />
          <CampoDeTexto
            rotulo="Senha"
            valor={senha}
            aoMudar={setSenha}
            senha
            erro={senhaCurta ? `Mínimo de ${SENHA_MINIMA} caracteres.` : null}
          />
        </View>

        {erro ? (
          <Text style={[texto.apoio, estilos.erro, { color: cores.acento }]}>
            {erro}
          </Text>
        ) : null}

        <BotaoPrimario
          rotulo="Criar conta"
          aoTocar={() => void registrar()}
          carregando={carregando}
          desabilitado={email.trim().length === 0 || senha.length < SENHA_MINIMA}
        />

        <View style={estilos.rodape}>
          <Text style={[texto.apoio, { color: cores.secundario }]}>Já tem conta?</Text>
          <LinkDeTexto rotulo="Entrar" aoTocar={aoIrParaEntrada} />
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
