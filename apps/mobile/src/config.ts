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

function lerExtra(): Extra {
  const bruto = Constants.expoConfig?.extra;
  if (!bruto) {
    throw new Error('app.json não tem expo.extra — a configuração do app sumiu.');
  }

  const limite = bruto.limiteGravacaoSegundos;
  if (typeof limite !== 'number' || !Number.isFinite(limite) || limite <= 0) {
    throw new Error(`extra.limiteGravacaoSegundos inválido: ${String(limite)}`);
  }

  const url = bruto.apiBaseUrl;
  if (typeof url !== 'string' || url.length === 0) {
    throw new Error(`extra.apiBaseUrl inválido: ${String(url)}`);
  }

  const sse = bruto.sseHabilitado;
  if (typeof sse !== 'boolean') {
    throw new Error(`extra.sseHabilitado inválido: ${String(sse)}`);
  }

  return { limiteGravacaoSegundos: limite, apiBaseUrl: url, sseHabilitado: sse };
}

export const config: Extra = lerExtra();
