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

import { StyleSheet, Text, View } from 'react-native';
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
        </View>
      ) : null}

      {/* 3. A correção, por último — o `feedback` fecha depois do áudio. */}
      {turno.correcao ? (
        <View
          style={[
            estilos.bolha,
            estilos.correcao,
            { backgroundColor: cores.superficie, borderLeftColor: cores.acento },
          ]}
        >
          <Text style={[texto.rotulo, { color: cores.acento }]}>
            {turno.correcao.has_mistakes ? 'CORREÇÃO' : 'SEM ERROS'}
          </Text>
          {turno.correcao.has_mistakes ? (
            <>
              <Text style={[texto.apoio, estilos.riscado, { color: cores.secundario }]}>
                {turno.correcao.original}
              </Text>
              <Text style={[texto.correcao, { color: cores.tinta }]}>
                {turno.correcao.corrected}
              </Text>
            </>
          ) : null}
          <Text style={[texto.apoio, { color: cores.secundario }]}>
            {turno.correcao.tip}
          </Text>
        </View>
      ) : null}

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
  correcao: {
    borderLeftWidth: 3,
  },
  riscado: {
    textDecorationLine: 'line-through',
  },
});
