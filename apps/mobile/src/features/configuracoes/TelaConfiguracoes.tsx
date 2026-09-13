/**
 * Configurações — quarta aba (CARD-059), sem artboard de referência.
 *
 * **Preferência de aparelho, não de conta** — por isso não depende da
 * autenticação que a aba Perfil espera (Fase 3). Duas seções nesta versão:
 * limite de gravação (leitura, nunca editável — o valor é regra de produto,
 * ver `config.ts`) e Sobre (versão instalada).
 *
 * **A seção de preferências de reprodução (velocidade padrão) fica de fora
 * de propósito**: ela controla um valor que só existe a partir do CARD-035
 * (`0.75×`/`1×`), que ainda não rodou nesta sessão do loop autônomo.
 * Construir o toggle antes do valor que ele controla é o botão morto que o
 * CARD-016 já evitou uma vez para `traduzir` — o mesmo raciocínio, adiado
 * para quem fechar o CARD-035.
 */

import Constants from 'expo-constants';
import { StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { config } from '@/config';
import { rotuloDoLimiteDeGravacao } from '@/features/configuracoes/rotulosDeConfiguracoes';
import { espaco, texto, useCores } from '@/theme/tokens';

export function TelaConfiguracoes() {
  const cores = useCores();
  const versao = Constants.expoConfig?.version ?? '—';

  return (
    <SafeAreaView style={[estilos.tela, { backgroundColor: cores.fundo }]}>
      <View style={estilos.conteudo}>
        <Text style={[texto.display, { color: cores.tinta }]}>Configurações</Text>

        <View style={estilos.secao}>
          <Text style={[texto.rotulo, { color: cores.secundario }]}>
            LIMITE DE GRAVAÇÃO
          </Text>
          <Text style={[texto.corpo, { color: cores.tinta }]}>
            {rotuloDoLimiteDeGravacao(config.limiteGravacaoSegundos)}
          </Text>
          <Text style={[texto.apoio, { color: cores.secundario }]}>
            A gravação para sozinha ao chegar neste tempo — é por isso que uma fala
            longa às vezes é cortada.
          </Text>
        </View>

        <View style={estilos.secao}>
          <Text style={[texto.rotulo, { color: cores.secundario }]}>SOBRE</Text>
          <Text style={[texto.corpo, { color: cores.tinta }]}>
            Voicecoach · versão {versao}
          </Text>
        </View>
      </View>
    </SafeAreaView>
  );
}

const estilos = StyleSheet.create({
  tela: { flex: 1 },
  conteudo: {
    flex: 1,
    padding: espaco.lg,
    gap: espaco.lg,
  },
  secao: {
    gap: espaco.xs,
  },
});
