/**
 * "Continuar com o Google" na web (CARD-064, ADR-0077) — Google Identity
 * Services (GIS), o script oficial do Google, sem pacote npm.
 *
 * **Por que o botão é desenhado pelo Google e não por nós.** O GIS só
 * entrega o `id_token` a partir de UI dele (o botão `renderButton` ou o
 * One Tap): não existe "abrir o popup a partir do meu botão" que devolva um
 * `id_token` — o fluxo de popup customizado devolve um *access token* OAuth,
 * que o backend não verifica (ele valida `id_token` contra o JWKS, ADR-0070).
 * O preço é o botão seguir a identidade visual do Google, não a nossa — o que
 * as diretrizes de marca do Google exigiriam de qualquer forma.
 *
 * O `id_token` que chega aqui tem `aud` igual ao client ID **Web** — por isso
 * o backend aceita `GOOGLE_WEB_CLIENT_ID` além do do iOS.
 */

import { useEffect, useRef, useState } from 'react';

import estilos from '@/ui/ui.module.css';

const SCRIPT_DO_GIS = 'https://accounts.google.com/gsi/client';

type RespostaDeCredencial = { credential: string };

type ApiDoGis = {
  accounts: {
    id: {
      initialize(opcoes: {
        client_id: string;
        callback: (resposta: RespostaDeCredencial) => void;
        ux_mode?: 'popup' | 'redirect';
      }): void;
      renderButton(
        elemento: HTMLElement,
        opcoes: {
          type?: 'standard' | 'icon';
          theme?: 'outline' | 'filled_blue' | 'filled_black';
          size?: 'large' | 'medium' | 'small';
          text?: 'continue_with' | 'signin_with' | 'signup_with';
          shape?: 'rectangular' | 'pill';
          width?: number;
          locale?: string;
        },
      ): void;
    };
  };
};

declare global {
  interface Window {
    google?: ApiDoGis;
  }
}

let carregamento: Promise<ApiDoGis> | null = null;

/** Carrega o script UMA vez por página, por mais botões que existam. */
function carregarGis(): Promise<ApiDoGis> {
  if (carregamento) return carregamento;
  carregamento = new Promise((resolver, rejeitar) => {
    if (window.google) {
      resolver(window.google);
      return;
    }
    const script = document.createElement('script');
    script.src = SCRIPT_DO_GIS;
    script.async = true;
    script.onload = () =>
      window.google
        ? resolver(window.google)
        : rejeitar(new Error('O script do Google carregou sem a API.'));
    script.onerror = () => {
      carregamento = null;
      rejeitar(new Error('Não foi possível carregar o login do Google.'));
    };
    document.head.appendChild(script);
  });
  return carregamento;
}

type Props = {
  clientId: string;
  aoReceberIdToken: (idToken: string) => void;
  aoFalhar: (mensagem: string) => void;
};

export function BotaoGoogle({ clientId, aoReceberIdToken, aoFalhar }: Props) {
  const lugar = useRef<HTMLDivElement>(null);
  const [pronto, setPronto] = useState(false);
  // O GIS guarda o callback do `initialize` — um `ref` deixa o botão usar
  // sempre a função mais nova sem reinicializar o Google a cada render.
  const aoReceber = useRef(aoReceberIdToken);
  aoReceber.current = aoReceberIdToken;

  useEffect(() => {
    let vivo = true;
    carregarGis()
      .then((google) => {
        if (!vivo || !lugar.current) return;
        google.accounts.id.initialize({
          client_id: clientId,
          callback: (resposta) => aoReceber.current(resposta.credential),
          ux_mode: 'popup',
        });
        google.accounts.id.renderButton(lugar.current, {
          type: 'standard',
          theme: 'outline',
          size: 'large',
          text: 'continue_with',
          shape: 'rectangular',
          width: 400,
          locale: 'pt-BR',
        });
        setPronto(true);
      })
      .catch((erro: unknown) => {
        if (vivo) aoFalhar(erro instanceof Error ? erro.message : String(erro));
      });
    return () => {
      vivo = false;
    };
  }, [clientId, aoFalhar]);

  return <div ref={lugar} aria-busy={!pronto} className={estilos.lugarDoGoogle} />;
}
