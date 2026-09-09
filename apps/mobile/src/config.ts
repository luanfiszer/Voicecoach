/**
 * Configuração do app, lida de `app.json > expo.extra` via `expo-constants`.
 *
 * Equivalente mental .NET: `appsettings.json` + `IOptions<T>` — declarativo,
 * versionado, validado uma vez no arranque. O que NÃO existe aqui é o
 * `pydantic-settings` do backend (ADR-0013): o Expo não valida `extra`, então
 * a validação é escrita à mão e falha ALTO, no import, e não em silêncio no
 * meio de uma gravação.
 *
 * Por que não constante no componente: o limite de duração é REGRA DE PRODUTO
 * (diagnóstico §7.4 — "cliente mede e limita duração na captura; servidor
 * valida ambos"), e ele tem um par do outro lado: `max_turn_audio_duration`,
 * hoje 120 s em `backend/src/voicecoach/config.py`. Se o cliente gravar mais
 * que o servidor aceita, o aluno fala, espera o upload inteiro e recebe um 413.
 * A folga entre 90 e 120 é o custo de rede que escolhemos não desperdiçar.
 */

import Constants from 'expo-constants';
import { NativeModules } from 'react-native';

type Extra = {
  limiteGravacaoSegundos: number;
  apiBaseUrl: string;
  /**
   * Liga o SSE. Desligada, o app usa só `GET /v1/turns/{id}` — o contrato de
   * recuo do ADR-0026 item 4.
   *
   * **A flag é ESCOPO, não conveniência**: o recuo que ninguém testa apodrece,
   * e um app que só saiba consumir SSE torna o `GET` um endpoint morto que o CI
   * acha que funciona.
   */
  sseHabilitado: boolean;
};

/**
 * A porta em que o backend escuta (`uvicorn --port 8000`).
 *
 * Constante, e não configuração: ela só é usada para *derivar* a URL do host do
 * bundler. Quem roda o backend em outro lugar tem o caminho certo, que é
 * `extra.apiBaseUrl` — uma configuração que já existe resolve melhor que duas.
 */
const PORTA_DA_API = 8000;

/**
 * De onde saiu o `apiBaseUrl` efetivo. Vai no log de arranque **junto com o
 * valor**: saber que a URL é `http://192.168.0.12:8000` importa menos do que
 * saber *por que* ela é essa.
 */
export type OrigemDaApi = 'extra' | 'bundler';

/**
 * O módulo nativo que sabe de onde o JavaScript foi carregado.
 *
 * Sem paralelo em C#: não é configuração nem variável de ambiente — é o próprio
 * runtime dizendo qual URL serviu o código que está executando agora.
 */
type SourceCode = {
  scriptURL?: string;
  getConstants?: () => { scriptURL?: string };
};

/**
 * O host do Metro, quando há um. **Duas fontes, porque os dois ambientes de
 * desenvolvimento respondem de formas diferentes** (medido no CARD-037):
 *
 * | Ambiente | `Constants.expoConfig.hostUri` | `SourceCode.scriptURL` |
 * |---|---|---|
 * | Expo Go | `"192.168.0.12:8081"` | a URL do bundle |
 * | **dev build** | **`undefined`** | a URL do bundle |
 * | produção | `undefined` | `file://…` (sem host) |
 *
 * O `hostUri` vem do *manifesto* que o Expo CLI entrega ao Expo Go — e num dev
 * build **não há manifesto**, porque o app é o seu próprio host (ADR-0054). O
 * que sobra em ambos é de onde o JavaScript veio, que é o que se quer saber.
 */
function hostDoBundler(): string | null {
  const hostUri = Constants.expoConfig?.hostUri;
  if (typeof hostUri === 'string' && hostUri.length > 0) {
    const host = hostUri.split('/')[0]?.split(':')[0];
    if (host && host.length > 0) return host;
  }

  const modulo = NativeModules.SourceCode as SourceCode | undefined;
  const scriptURL = modulo?.getConstants?.().scriptURL ?? modulo?.scriptURL;
  // Em produção o bundle é `file://…`: não há host, e cair aqui é o caminho
  // certo para o erro alto do terceiro degrau.
  if (typeof scriptURL !== 'string' || !scriptURL.startsWith('http')) return null;
  const semEsquema = scriptURL.split('://')[1];
  const host = semEsquema?.split('/')[0]?.split(':')[0];
  return host && host.length > 0 ? host : null;
}

/**
 * Resolve o `apiBaseUrl` em três degraus (ADR-0054 item 6).
 *
 * **`localhost` não pode ser default** (CARD-037): no Simulador ele funciona,
 * porque o Simulador compartilha a pilha de rede do Mac; num iPhone ele aponta
 * para o **próprio iPhone** e falha de um jeito que não se lê como configuração
 * errada. Derivar do host do bundler resolve os dois ambientes sem editar nada,
 * e sobrevive ao IP que o DHCP troca: se o Metro alcança o aparelho, o backend
 * também alcança — é a mesma máquina.
 */
function resolverApiBaseUrl(bruto: unknown): { url: string; origem: OrigemDaApi } {
  // 1. Override explícito. É o degrau que o CARD-038 vai usar quando o backend
  //    sair da LAN e passar a viver atrás de um túnel.
  if (typeof bruto === 'string' && bruto.length > 0) {
    return { url: bruto, origem: 'extra' };
  }
  if (bruto !== undefined && bruto !== null) {
    throw new Error(`extra.apiBaseUrl inválido: ${String(bruto)}`);
  }

  // 2. O host de onde o JavaScript veio, com a porta da API.
  const host = hostDoBundler();
  if (host) {
    return { url: `http://${host}:${PORTA_DA_API}`, origem: 'bundler' };
  }

  // 3. Nada resolveu. Falhar no arranque é melhor que falhar no meio da
  //    primeira gravação do aluno.
  throw new Error(
    'Não foi possível resolver o endereço da API: não há `extra.apiBaseUrl` em ' +
      'app.json e o JavaScript não veio de um bundler por HTTP. ' +
      'Defina `expo.extra.apiBaseUrl` com a URL do backend.',
  );
}

function lerExtra(): Extra {
  const bruto = Constants.expoConfig?.extra;
  if (!bruto) {
    throw new Error('app.json não tem expo.extra — a configuração do app sumiu.');
  }

  const limite = bruto.limiteGravacaoSegundos;
  if (typeof limite !== 'number' || !Number.isFinite(limite) || limite <= 0) {
    throw new Error(`extra.limiteGravacaoSegundos inválido: ${String(limite)}`);
  }

  const api = resolverApiBaseUrl(bruto.apiBaseUrl);

  const sse = bruto.sseHabilitado;
  if (typeof sse !== 'boolean') {
    throw new Error(`extra.sseHabilitado inválido: ${String(sse)}`);
  }

  // O critério de aceite do CARD-037 se lê no log de arranque: num aparelho
  // físico, a primeira pergunta é sempre "com quem esse app está falando?".
  console.info(`[config] apiBaseUrl=${api.url} (origem: ${api.origem})`);

  return {
    limiteGravacaoSegundos: limite,
    apiBaseUrl: api.url,
    sseHabilitado: sse,
  };
}

export const config: Extra = lerExtra();
