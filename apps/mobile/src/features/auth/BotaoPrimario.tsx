/**
 * O botão cheio, acento sólido, do artboard 11 ("Criar conta"). Reusado nas
 * cinco telas de auth (CARD-050).
 *
 * `variante="destrutivo"` (CARD-051) troca só a cor de fundo para
 * `cores.perigo` — a única ação irreversível do app (excluir a conta) é o
 * primeiro a precisar dela.
 *
 * `variante="secundario"` (CARD-060) é o contorno — sem artboard próprio
 * (login social não existia quando o 11 foi desenhado): fundo
 * `cores.superficie`, borda `cores.secundario`, texto `cores.tinta`. Existe
 * para que "Entrar"/"Criar conta" continue sendo a ÚNICA ação de acento
 * cheio da tela — um segundo botão sólido do mesmo peso visual competiria
 * pela atenção que o formulário por e-mail já tem.
 *
 * `icone` (CARD-060) é o elemento de marca (Google/Apple) antes do rótulo —
 * `ReactNode` solto, não um nome de glifo: o "G" do Google é colorido em
 * quatro tons (`LogoGoogle`, SVG), e um glifo de fonte de ícone só pinta o
 * todo de uma cor só. Quem monta o ícone (com a cor certa, quando for mono)
 * é o chamador — este componente só reserva o espaço antes do texto.
 */

import type { ReactNode } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import { alvo, espaco, texto, useCores } from '@/theme/tokens';

type Props = {
  rotulo: string;
  aoTocar: () => void;
  carregando?: boolean;
  desabilitado?: boolean;
  variante?: 'primario' | 'destrutivo' | 'secundario';
  icone?: ReactNode;
};

export function BotaoPrimario({
  rotulo,
  aoTocar,
  carregando = false,
  desabilitado = false,
  variante = 'primario',
  icone,
}: Props) {
  const cores = useCores();
  const inativo = carregando || desabilitado;
  const secundario = variante === 'secundario';
  const corDoConteudo = secundario ? cores.tinta : cores.sobreAcento;

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={rotulo}
      accessibilityState={{ disabled: inativo }}
      onPress={inativo ? undefined : aoTocar}
      style={({ pressed }) => [
        estilos.botao,
        secundario
          ? {
              backgroundColor: cores.superficie,
              borderWidth: 1.5,
              borderColor: cores.secundario,
            }
          : {
              backgroundColor: variante === 'destrutivo' ? cores.perigo : cores.acento,
            },
        { opacity: inativo ? 0.6 : pressed ? 0.85 : 1 },
      ]}
    >
      {carregando ? (
        <ActivityIndicator color={corDoConteudo} />
      ) : (
        <View style={estilos.conteudo}>
          {icone}
          <Text style={[texto.corpo, { color: corDoConteudo, fontWeight: '700' }]}>
            {rotulo}
          </Text>
        </View>
      )}
    </Pressable>
  );
}

const estilos = StyleSheet.create({
  botao: {
    minHeight: alvo.minimo + espaco.sm,
    borderRadius: 999,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: espaco.lg,
  },
  conteudo: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: espaco.sm,
  },
});
