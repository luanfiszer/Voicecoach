import { type ReactNode, useEffect, useRef } from 'react';

import estilos from '@/features/conversa/conversa.module.css';

/**
 * A janela que cobre a conversa (artboards 13–16). `<dialog>`-like com o
 * foco levado para dentro ao abrir — quem usa teclado não fica preso atrás.
 */
export function Overlay({ titulo, children }: { titulo: string; children: ReactNode }) {
  const caixa = useRef<HTMLDivElement>(null);
  useEffect(() => {
    caixa.current?.querySelector<HTMLElement>('button')?.focus();
  }, []);
  return (
    <div className={estilos.fundoDoOverlay}>
      <div
        ref={caixa}
        className={estilos.overlay}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="overlay-titulo"
      >
        <h2 id="overlay-titulo">{titulo}</h2>
        {children}
      </div>
    </div>
  );
}
