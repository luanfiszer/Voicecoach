/**
 * A sessão na árvore de componentes: um contexto com a `SessaoWeb` e o
 * estado observável. Quem decide se a tela é a de login ou a do app é o
 * estado, não a navegação — mesmo desenho do mobile (CARD-050).
 */

import { criarCliente } from '@voicecoach/api-client';
import {
  createContext,
  type ReactNode,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';

import { config } from '@/config';
import {
  criarSessaoWeb,
  type EstadoDaSessao,
  type SessaoWeb,
  travaDoNavegador,
} from '@/features/auth/sessaoWeb';

type ValorDaSessao = SessaoWeb & { estado: EstadoDaSessao };

const Contexto = createContext<ValorDaSessao | null>(null);

export function ProvedorDeSessao({ children }: { children: ReactNode }) {
  const [estado, setEstado] = useState<EstadoDaSessao>('carregando');

  const sessao = useMemo(
    () =>
      criarSessaoWeb({
        cliente: criarCliente({ baseUrl: config.apiBaseUrl }),
        trava: travaDoNavegador(
          typeof navigator !== 'undefined' ? navigator.locks : undefined,
        ),
        aoMudarEstado: setEstado,
      }),
    [],
  );

  useEffect(() => {
    void sessao.inicializar();
  }, [sessao]);

  const valor = useMemo(() => ({ ...sessao, estado }), [sessao, estado]);
  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}

export function useSessao(): ValorDaSessao {
  const valor = useContext(Contexto);
  if (valor === null) {
    throw new Error('useSessao fora do <ProvedorDeSessao>.');
  }
  return valor;
}

/** Um client da API cujas chamadas já levam o access token e renovam sozinhas. */
export function useClienteAutenticado() {
  const { fetchAutenticado } = useSessao();
  return useMemo(
    () => criarCliente({ baseUrl: config.apiBaseUrl, fetch: fetchAutenticado }),
    [fetchAutenticado],
  );
}
