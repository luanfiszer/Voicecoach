/**
 * Redefinir senha a partir do código do e-mail (CARD-050).
 *
 * **O código é colado à mão, não um deep link.** O e-mail que o CARD-049
 * manda aponta para um endpoint que é `POST` no servidor — um link comum,
 * clicado num cliente de e-mail, não tem como coletar a senha nova nem
 * disparar um `POST`. Ligar isto a um deep link (`voicecoach://...`) e a uma
 * página web de fallback é trabalho de infraestrutura que nenhum critério de
 * aceite deste card pede — fica como próximo passo de UX, não como parte
 * pela metade: a redefinição funciona ponta a ponta assim, só sem o toque
 * único.
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

const SENHA_MINIMA = 8;

type Props = {
  aoConcluir: () => void;
  aoVoltarParaEntrada: () => void;
};

export function TelaRedefinirSenha({ aoConcluir, aoVoltarParaEntrada }: Props) {
  const cores = useCores();
  const sessao = useSessao();
  const [codigo, setCodigo] = useState('');
  const [novaSenha, setNovaSenha] = useState('');
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const redefinir = async () => {
    setErro(null);
    setCarregando(true);
    try {
      await sessao.redefinirSenha(codigo.trim(), novaSenha);
      aoConcluir();
    } catch (falha) {
      setErro(mensagemDeErroDeAuth(falha));
    } finally {
      setCarregando(false);
    }
  };

  return (
    <SafeAreaView style={[estilos.tela, { backgroundColor: cores.fundo }]}>
      <View style={estilos.conteudo}>
        <Text style={[texto.display, { color: cores.tinta }]}>Redefinir senha</Text>
        <Text style={[texto.apoio, { color: cores.secundario }]}>
          Cole aqui o código que veio no e-mail e escolha uma senha nova.
        </Text>

        <CampoDeTexto rotulo="Código do e-mail" valor={codigo} aoMudar={setCodigo} />
        <CampoDeTexto
          rotulo="Nova senha"
          valor={novaSenha}
          aoMudar={setNovaSenha}
          senha
          erro={
            novaSenha.length > 0 && novaSenha.length < SENHA_MINIMA
              ? `Mínimo de ${SENHA_MINIMA} caracteres.`
              : null
          }
        />

        {erro ? (
          <Text style={[texto.apoio, { color: cores.acento }]}>{erro}</Text>
        ) : null}

        <BotaoPrimario
          rotulo="Redefinir senha"
          aoTocar={() => void redefinir()}
          carregando={carregando}
          desabilitado={codigo.trim().length === 0 || novaSenha.length < SENHA_MINIMA}
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
