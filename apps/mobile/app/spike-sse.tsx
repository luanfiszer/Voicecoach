/**
 * SPIKE — descartável, e marcado como tal.
 *
 * Pergunta que ele responde (requisito do CARD-011, vindo do ADR-0026):
 * **dá para consumir o SSE do backend DENTRO DO EXPO GO, sem dev build?**
 *
 * O `EventSource` nativo não aceita cabeçalho `Authorization` (ADR-0026), então
 * os candidatos são (a) `react-native-sse`, um polyfill com headers, e (b) ler
 * o corpo da resposta como stream. Esta tela compara os dois `fetch` que
 * existem no app — o GLOBAL do React Native e o de `expo/fetch` — contra o
 * endpoint real `GET /v1/turns/{id}/events` do CARD-010.
 *
 * Não é implementação: o consumo de verdade é do CARD-012. Esta tela sai do
 * repositório quando aquele card fechar, ou vira o teste de fumaça dele.
 */

import { fetch as expoFetch } from 'expo/fetch';
import { useLocalSearchParams } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { config } from '@/config';
import { alvo, espaco, texto, useCores } from '@/theme/tokens';

type Linha = { t: number; texto: string };

/**
 * Parser mínimo de `text/event-stream`: separa por linha em branco.
 *
 * ARMADILHA MEDIDA NESTE SPIKE: o `sse-starlette` termina cada linha com
 * **CRLF**, então o separador de eventos é `\r\n\r\n` e não `\n\n`. Procurar
 * `\n\n` faz o stream chegar inteiro e NENHUM evento ser reconhecido — falha
 * silenciosa, sem erro, que parece "o SSE não funciona no Expo Go". Daí a
 * normalização antes de qualquer split.
 */
function* eventos(buffer: string): Generator<{ evento: string; dados: string }> {
  for (const bloco of buffer.split('\n\n')) {
    if (!bloco.trim()) continue;
    let evento = 'message';
    const dados: string[] = [];
    for (const linha of bloco.split('\n')) {
      if (linha.startsWith('event:')) evento = linha.slice(6).trim();
      if (linha.startsWith('data:')) dados.push(linha.slice(5).trim());
    }
    yield { evento, dados: dados.join('\n') };
  }
}

export default function SpikeSse() {
  const cores = useCores();
  const parametros = useLocalSearchParams<{ turnId?: string; auto?: string }>();
  const [turnId, setTurnId] = useState(parametros.turnId ?? '');
  const [linhas, setLinhas] = useState<Linha[]>([]);

  // `useCallback` sem dependências porque `setLinhas` é estável: sem isto,
  // `registrar` nasce nova a cada render e o `useCallback` de `consumir`
  // deixaria de ser estável — que é justamente o que o linter apontou.
  const registrar = useCallback((texto: string) => {
    setLinhas((atual) => [...atual, { t: Date.now(), texto }]);
  }, []);

  const consumir = useCallback(
    async function consumir(
      qual: 'global' | 'expo',
      id: string = turnId,
      limpar = true,
    ) {
      if (limpar) setLinhas([]);
      const inicio = Date.now();
      const url = `${config.apiBaseUrl}/v1/turns/${id}/events`;
      const impl = qual === 'expo' ? expoFetch : fetch;
      registrar(`→ ${qual}: ${url}`);

      try {
        const resposta = await impl(url, { headers: { Accept: 'text/event-stream' } });
        registrar(`status ${resposta.status}; body é ${typeof resposta.body}`);

        const corpo = resposta.body;
        if (!corpo) {
          // O caminho que prova a diferença: sem `body`, só resta esperar o
          // texto inteiro — que é o oposto de entrega progressiva.
          const tudo = await resposta.text();
          registrar(`SEM STREAM: ${tudo.length} bytes de uma vez só`);
          return;
        }

        const leitor = (corpo as ReadableStream<Uint8Array>).getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let pedacos = 0;

        while (true) {
          const { done, value } = await leitor.read();
          if (done) break;
          pedacos += 1;
          buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');
          const corte = buffer.lastIndexOf('\n\n');
          if (corte === -1) continue;
          for (const e of eventos(buffer.slice(0, corte))) {
            registrar(
              `+${Date.now() - inicio}ms  ${e.evento}: ${e.dados.slice(0, 70)}`,
            );
          }
          buffer = buffer.slice(corte + 2);
        }
        registrar(`fim — ${pedacos} leituras do stream`);
      } catch (erro) {
        registrar(`ERRO: ${String(erro)}`);
      }
    },
    [turnId, registrar],
  );

  // Disparo por deep link: `voicecoach://spike-sse?turnId=…&auto=1` roda as
  // duas implementações em sequência, sem ninguém tocar na tela. É o que
  // torna o spike executável a partir do terminal.
  useEffect(() => {
    const id = parametros.turnId;
    if (!id || parametros.auto !== '1') return;
    void (async () => {
      await consumir('global', id, true);
      await consumir('expo', id, false);
    })();
  }, [parametros.turnId, parametros.auto, consumir]);

  return (
    <SafeAreaView style={[estilos.tela, { backgroundColor: cores.fundo }]}>
      <Text style={[texto.display, { color: cores.tinta }]}>Spike SSE</Text>

      <TextInput
        value={turnId}
        onChangeText={setTurnId}
        placeholder="turn_id"
        autoCapitalize="none"
        placeholderTextColor={cores.secundario}
        style={[
          estilos.campo,
          { color: cores.tinta, borderColor: cores.secundario },
          texto.apoio,
        ]}
      />

      <View style={estilos.botoes}>
        <Pressable
          style={[estilos.botao, { backgroundColor: cores.acento }]}
          onPress={() => void consumir('global')}
        >
          <Text style={estilos.rotulo}>fetch global (RN)</Text>
        </Pressable>
        <Pressable
          style={[estilos.botao, { backgroundColor: cores.acento }]}
          onPress={() => void consumir('expo')}
        >
          <Text style={estilos.rotulo}>expo/fetch</Text>
        </Pressable>
      </View>

      <ScrollView style={estilos.log}>
        {linhas.map((l) => (
          <Text key={`${l.t}-${l.texto}`} style={[texto.apoio, { color: cores.tinta }]}>
            {l.texto}
          </Text>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

const estilos = StyleSheet.create({
  tela: { flex: 1, padding: espaco.md, gap: espaco.sm },
  campo: {
    minHeight: alvo.minimo,
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: espaco.sm,
  },
  botoes: { flexDirection: 'row', gap: espaco.sm },
  botao: {
    flex: 1,
    minHeight: alvo.minimo,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  rotulo: { color: '#FFFFFF', fontWeight: '600' },
  log: { flex: 1 },
});
