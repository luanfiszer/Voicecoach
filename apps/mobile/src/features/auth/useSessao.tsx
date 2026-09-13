/**
 * O contexto React sobre `sessaoAutenticada.ts` — a única ponte entre a
 * máquina de estados pura e a árvore de componentes.
 *
 * **Uma instância por processo do app**, criada com `useState` (não
 * `useMemo`) de propósito: `useMemo` não garante que o valor sobreviva a um
 * *strict mode* que remonta o componente — `useState(() => ...)` roda o
 * inicializador uma vez só e é o jeito correto de guardar algo com
 * identidade própria (a sessão tem estado interno, não é um valor derivado).
 */

import { type Cliente, criarCliente } from '@voicecoach/api-client';
import { createContext, type ReactNode, useContext, useEffect, useState } from 'react';

import { config } from '@/config';
import { armazenamentoSeguro } from '@/features/auth/armazenamentoDeToken';
import {
  criarSessaoAutenticada,
  type EstadoDaSessao,
  type SessaoAutenticada,
} from '@/features/auth/sessaoAutenticada';

export type ContextoDeSessao = SessaoAutenticada & { estado: EstadoDaSessao };

const SessaoContext = createContext<ContextoDeSessao | null>(null);

export function ProvedorDeSessao({ children }: { children: ReactNode }) {
  const [estado, setEstado] = useState<EstadoDaSessao>('carregando');
  const [sessao] = useState<SessaoAutenticada>(() => {
    // Cliente SEM `fetchAutenticado`: login/registro/refresh/logout não
    // levam `Authorization` (são as próprias rotas que emitem o token), e
    // usar o `fetchAutenticado` aqui criaria uma dependência circular —
    // "para renovar preciso do fetch que renova".
    const clienteSemAuth: Cliente = criarCliente({ baseUrl: config.apiBaseUrl });
    return criarSessaoAutenticada({
      cliente: clienteSemAuth,
      armazenamento: armazenamentoSeguro,
      aoMudarEstado: setEstado,
    });
  });

  useEffect(() => {
    void sessao.inicializar();
    // `sessao` é estável pela vida do componente (criada uma vez no
    // `useState` acima) — incluir na dependência não causaria uma segunda
    // chamada, mas documenta a intenção de rodar de novo se a instância
    // mudasse.
  }, [sessao]);

  const valor: ContextoDeSessao = { ...sessao, estado };

  return <SessaoContext.Provider value={valor}>{children}</SessaoContext.Provider>;
}

export function useSessao(): ContextoDeSessao {
  const contexto = useContext(SessaoContext);
  if (contexto === null) {
    throw new Error('useSessao() precisa estar dentro de <ProvedorDeSessao>.');
  }
  return contexto;
}
