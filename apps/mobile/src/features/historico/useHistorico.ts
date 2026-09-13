/**
 * O estado da tela de Histórico (CARD-029): busca, carrega, erro, vazio.
 *
 * **Mais simples que `useTurno` de propósito.** Não há SSE, não há retomada,
 * não há `AppState` a observar — é uma leitura só, disparada ao montar a tela.
 * `recarregar` existe para o gesto explícito de puxar-para-atualizar.
 *
 * O `AbortController` ainda mora aqui, e pela mesma razão do `useTurno`: sem
 * ele, uma resposta que chega depois de o componente desmontar tentaria
 * `setState` num componente morto.
 */

import {
  type Cliente,
  criarCliente,
  type SessaoDoHistorico,
} from '@voicecoach/api-client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { config } from '@/config';
import { useSessao } from '@/features/auth/useSessao';

export type EstadoDoHistorico =
  | { tipo: 'carregando' }
  | { tipo: 'vazio' }
  | { tipo: 'pronto'; sessoes: SessaoDoHistorico[] }
  | { tipo: 'falhou'; mensagem: string };

export type Historico = {
  estado: EstadoDoHistorico;
  recarregar: () => void;
};

/**
 * Traduz o que `ErroDaApi`/`ErroDeRede` sabem dizer numa frase para o aluno.
 *
 * Extraída do hook por ser lógica pura, mas não tem teste próprio: as duas
 * classes de erro já têm o comportamento delas testado em
 * `packages/api-client`, e o que resta aqui é só concatenar — cobrir isso
 * separadamente testaria o `instanceof`, não uma regra do produto.
 */
function mensagemDeErro(erro: unknown): string {
  if (erro instanceof Error) return erro.message;
  return 'Não foi possível carregar o histórico.';
}

export function useHistorico(cliente?: Cliente): Historico {
  const { fetchAutenticado } = useSessao();
  const clienteEfetivo = useMemo(
    () =>
      cliente ?? criarCliente({ baseUrl: config.apiBaseUrl, fetch: fetchAutenticado }),
    [cliente, fetchAutenticado],
  );
  const [estado, setEstado] = useState<EstadoDoHistorico>({ tipo: 'carregando' });
  const controlador = useRef<AbortController | null>(null);

  const buscar = useCallback(() => {
    controlador.current?.abort();
    const meu = new AbortController();
    controlador.current = meu;
    setEstado({ tipo: 'carregando' });

    clienteEfetivo
      .listarSessoes(undefined, meu.signal)
      .then((resposta) => {
        if (meu.signal.aborted) return;
        setEstado(
          resposta.sessions.length === 0
            ? { tipo: 'vazio' }
            : { tipo: 'pronto', sessoes: resposta.sessions },
        );
      })
      .catch((erro: unknown) => {
        if (meu.signal.aborted) return;
        setEstado({ tipo: 'falhou', mensagem: mensagemDeErro(erro) });
      });
  }, [clienteEfetivo]);

  useEffect(() => {
    buscar();
    return () => controlador.current?.abort();
  }, [buscar]);

  return { estado, recarregar: buscar };
}
