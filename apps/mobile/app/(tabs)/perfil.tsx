/**
 * Perfil — mínimo funcional (CARD-050): só "Sair" por enquanto.
 *
 * O CARD-029/artboard 12 completo (saldo de cota, dados da conta) continua
 * fora daqui — depende de mais do que login, e o CARD-051 (delete de conta)
 * é quem fecha esta tela de vez. O que o CARD-050 promete entregar é só "a
 * tela de conta que o CARD-051 completa", e login sem logout não é sessão
 * de verdade: o aluno precisa de como sair.
 */

import { StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { BotaoPrimario } from '@/features/auth/BotaoPrimario';
import { useSessao } from '@/features/auth/useSessao';
import { espaco, texto, useCores } from '@/theme/tokens';

export default function Rota() {
  const cores = useCores();
  const sessao = useSessao();

  return (
    <SafeAreaView style={[estilos.tela, { backgroundColor: cores.fundo }]}>
      <View style={estilos.conteudo}>
        <Text style={[texto.display, { color: cores.tinta }]}>Perfil</Text>
        <Text style={[texto.apoio, { color: cores.secundario }]}>
          Saldo de cota e dados da conta chegam com o CARD-051.
        </Text>
        <View style={estilos.botao}>
          <BotaoPrimario rotulo="Sair" aoTocar={() => void sessao.sair()} />
        </View>
      </View>
    </SafeAreaView>
  );
}

const estilos = StyleSheet.create({
  tela: { flex: 1 },
  conteudo: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: espaco.md,
    padding: espaco.lg,
  },
  botao: {
    width: '100%',
    marginTop: espaco.lg,
  },
});
