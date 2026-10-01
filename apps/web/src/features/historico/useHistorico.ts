/**
 * O estado da tela de Histórico — o `useHistorico` do mobile (CARD-029), com
 * o client autenticado da web. O `AbortController` evita `setState` depois
 * de a tela sair (o aluno trocou de aba antes de a lista chegar).
 */

import type { SessaoDoHistorico } from '@voicecoach/api-client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { mensagemDeErro } from '@/features/auth/mensagensDeErro';
import { useClienteAutenticado } from '@/features/auth/useSessao';

export type EstadoDoHistorico =
  | { tipo: 'carregando' }
  | { tipo: 'vazio' }
  | { tipo: 'pronto'; sessoes: SessaoDoHistorico[] }
  | { tipo: 'falhou'; mensagem: string };

export function useHistorico(): { estado: EstadoDoHistorico; recarregar: () => void } {
  const cliente = useClienteAutenticado();
  const [estado, setEstado] = useState<EstadoDoHistorico>({ tipo: 'carregando' });
  const controlador = useRef<AbortController | null>(null);

  const buscar = useCallback(() => {
    controlador.current?.abort();
    const meu = new AbortController();
    controlador.current = meu;
    setEstado({ tipo: 'carregando' });

    cliente
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
  }, [cliente]);

  useEffect(() => {
    buscar();
    return () => controlador.current?.abort();
  }, [buscar]);

  return { estado, recarregar: buscar };
}
