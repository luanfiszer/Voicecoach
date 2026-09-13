/**
 * A cascata na tela — **na ordem em que ela acontece de verdade**.
 *
 * O artboard 05 (*"Áudio a caminho… / Você já pode ler; o áudio toca sozinho
 * quando chegar"*) é de 2026-08-17, **anterior à cascata**, e descreve a ordem
 * invertida: texto primeiro, áudio depois. Com o ADR-0022/0023 o **áudio vem
 * primeiro**, em 3–6 trechos, e o texto da correção fecha por último. Montar
 * esta lista na ordem desenhada nasceria errado — a divergência está registrada
 * em `docs/design/README.md` e continua registrada aqui.
 *
 * A invariante do ADR-0023 item 6 é visível neste arquivo: quando o turn falha
 * **depois** de entregar trechos, o erro aparece **abaixo** do que já foi
 * ouvido, sem apagá-lo. O aluno ouviu; a tela tem de continuar dizendo que ele
 * ouviu.
 */

import { Pressable, StyleSheet, Text, View } from 'react-native';
import { rotuloDoBotaoDeTraduzir } from '@/features/turno/rotuloDaTraducao';
import { rotuloDaSeveridade, rotuloDoTipo } from '@/features/turno/rotulosDeCorrecao';
import type { Turno } from '@/features/turno/useTurno';
import { espaco, texto, useCores } from '@/theme/tokens';

export function ListaDoTurno({ turno }: { turno: Turno }) {
  const cores = useCores();

  if (turno.estado === 'ocioso') return null;

  return (
    <View style={estilos.lista}>
      {/* 1. A fala do aluno, assim que o STT fecha. */}
      {turno.transcricao ? (
        <View style={[estilos.bolha, { backgroundColor: cores.superficie }]}>
          <Text style={[texto.rotulo, { color: cores.secundario }]}>VOCÊ DISSE</Text>
          <Text style={[texto.corpo, { color: cores.tinta }]}>{turno.transcricao}</Text>
        </View>
      ) : (
        <Text style={[texto.apoio, { color: cores.secundario }]}>
          {turno.estado === 'enviando' ? 'Enviando sua fala…' : 'Transcrevendo…'}
        </Text>
      )}

      {/* 2. O ÁUDIO — antes do texto do feedback. É a ordem da cascata. */}
      {turno.trechos.length > 0 ? (
        <View style={[estilos.bolha, { backgroundColor: cores.superficie }]}>
          <Text style={[texto.rotulo, { color: cores.secundario }]}>PROFESSOR</Text>
          {turno.trechos.map((trecho) => (
            <Text
              key={trecho.index}
              style={[
                texto.corpo,
                {
                  color: turno.tocando === trecho.index ? cores.acento : cores.tinta,
                },
              ]}
            >
              {trecho.text}
            </Text>
          ))}

          {/* O botão `traduzir` (CARD-058): só quando há resposta a
              traduzir, nunca antes do turn concluir. */}
          {turno.estado === 'concluido' ? (
            <View style={estilos.traducao}>
              {turno.traducao.fase === 'traduzido' && turno.traducao.texto ? (
                <Text style={[texto.apoio, { color: cores.secundario }]}>
                  {turno.traducao.texto}
                </Text>
              ) : (
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel="Traduzir"
                  disabled={turno.traducao.fase === 'traduzindo'}
                  onPress={() => void turno.traduzir()}
                  hitSlop={espaco.sm}
                >
                  <Text style={[texto.rotulo, { color: cores.acento }]}>
                    {rotuloDoBotaoDeTraduzir(turno.traducao.fase)}
                  </Text>
                </Pressable>
              )}
            </View>
          ) : null}
        </View>
      ) : null}

      {/* 3. As correções, por último — o `feedback` fecha depois do áudio.
          Regra de produto preservada do protótipo (CARD-016, diagnóstico
          §5): sem correção, sem card — nenhuma, nem uma de afirmação
          positiva. Resposta só em áudio é o desfecho natural e mais comum. */}
      {turno.correcoes.map((correcao) => (
        <View
          key={correcao.index}
          style={[
            estilos.bolha,
            estilos.correcao,
            { backgroundColor: cores.superficie, borderLeftColor: cores.acento },
          ]}
        >
          <View style={estilos.badges}>
            <Text style={[texto.rotulo, { color: cores.acento }]}>
              {rotuloDoTipo(correcao.tipo).toUpperCase()}
            </Text>
            <Text style={[texto.rotulo, { color: cores.secundario }]}>
              {rotuloDaSeveridade(correcao.severidade).toUpperCase()}
            </Text>
          </View>
          <Text style={[texto.apoio, estilos.riscado, { color: cores.secundario }]}>
            {correcao.original}
          </Text>
          <Text style={[texto.correcao, { color: cores.tinta }]}>
            {correcao.corrigido}
          </Text>
          <Text style={[texto.apoio, { color: cores.secundario }]}>
            {correcao.explicacao}
          </Text>
        </View>
      ))}

      {/* 3b. Áudio indisponível — texto preservado, NUNCA erro fatal
          (ADR-0024 item 5). A URL do trecho é assinada e de vida curta; se ela
          expirar e nem o áudio inteiro existir, o aluno perde o som, não a aula. */}
      {turno.audioIndisponivel ? (
        <View style={[estilos.bolha, { backgroundColor: cores.superficie }]}>
          <Text style={[texto.rotulo, { color: cores.secundario }]}>
            SEM ÁUDIO AGORA
          </Text>
          <Text style={[texto.apoio, { color: cores.secundario }]}>
            O áudio desta resposta não está mais disponível. O texto continua aqui.
          </Text>
        </View>
      ) : null}

      {/* 4. A falha, SEM apagar o que veio acima (ADR-0023 item 6). */}
      {turno.erro ? (
        <View style={[estilos.bolha, { backgroundColor: cores.superficie }]}>
          <Text style={[texto.rotulo, { color: cores.acento }]}>
            {turno.entregaParcial ? 'A RESPOSTA FICOU PELA METADE' : 'NÃO DEU CERTO'}
          </Text>
          <Text style={[texto.apoio, { color: cores.secundario }]}>
            {turno.entregaParcial
              ? 'O que você já ouviu continua aqui. O resto não chegou.'
              : turno.erro}
          </Text>
        </View>
      ) : null}
    </View>
  );
}

const estilos = StyleSheet.create({
  lista: {
    width: '100%',
    gap: espaco.sm,
  },
  bolha: {
    borderRadius: 14,
    padding: espaco.md,
    gap: espaco.xs,
  },
  badges: {
    flexDirection: 'row',
    gap: espaco.sm,
  },
  correcao: {
    borderLeftWidth: 3,
  },
  traducao: {
    marginTop: espaco.xs,
  },
  riscado: {
    textDecorationLine: 'line-through',
  },
});
