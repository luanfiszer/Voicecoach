/**
 * A porta de entrada do pacote (ADR-0008).
 *
 * Duas coisas saem daqui e nada além: os **tipos gerados** do OpenAPI e o
 * **client HTTP fino**. Quem quiser falar com o backend importa daqui — montar
 * URL de backend em componente é a violação que o `README.md` deste pacote e a
 * skill `voicecoach-cliente` proíbem por nome.
 */

export {
  type AcompanhamentoDoTurn,
  type Cliente,
  criarCliente,
  type EnvioDeTurn,
  ErroDaApi,
  ErroDeStream,
  type EventoDoTurn,
  type OpcoesDoCliente,
  type Sessao,
  type Trecho,
  type Turn,
  type TurnAceito,
} from './cliente';
export type { components, operations, paths } from './schema';
