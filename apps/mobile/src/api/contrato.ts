/**
 * Os tipos do backend, vindos do OpenAPI — nunca escritos à mão (ADR-0008).
 *
 * Este arquivo é só uma camada de NOMES: `components['schemas']['TurnResponse']`
 * é o caminho gerado, e ninguém quer lê-lo espalhado pelo app. O que ele NÃO
 * faz é redeclarar nada: se o backend renomear um campo, `pnpm run typecheck`
 * fica vermelho aqui e em quem usa — que é exatamente a promessa do ADR-0008
 * ("mudança de API quebra os clientes em BUILD, não em runtime").
 *
 * O client HTTP (baseURL, token, retry, `Idempotency-Key`) mora em
 * `packages/api-client` e entra no CARD-012, quando houver quem o consuma.
 */

import type { components } from '@voicecoach/api-client';

export type Turn = components['schemas']['TurnResponse'];
export type TurnAceito = components['schemas']['TurnAcceptedResponse'];
export type Sessao = components['schemas']['SessionResponse'];
export type Trecho = components['schemas']['ChunkPayload'];
export type EtapaDoTurn = components['schemas']['TurnStage'];
