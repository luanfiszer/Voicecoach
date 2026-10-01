import type { ReactNode } from 'react';

import estilos from '@/ui/ui.module.css';

type Props = {
  rotulo: string;
  aoClicar?: () => void;
  carregando?: boolean;
  desabilitado?: boolean;
  variante?: 'primario' | 'secundario' | 'destrutivo';
  /** `submit` dentro de um `<form>`: o Enter do teclado envia sozinho. */
  tipo?: 'button' | 'submit';
  icone?: ReactNode;
};

/**
 * O botão da web — as mesmas três variantes do `BotaoPrimario` do mobile
 * (acento cheio, contorno, destrutivo). `aria-busy` diz ao leitor de tela o
 * que o spinner diz aos olhos.
 */
export function Botao({
  rotulo,
  aoClicar,
  carregando = false,
  desabilitado = false,
  variante = 'primario',
  tipo = 'button',
  icone,
}: Props) {
  return (
    <button
      type={tipo}
      className={`${estilos.botao} ${estilos[variante]}`}
      onClick={aoClicar}
      disabled={desabilitado || carregando}
      aria-busy={carregando}
    >
      {carregando ? (
        <span className={estilos.girando} aria-hidden="true" />
      ) : (
        <>
          {icone}
          {rotulo}
        </>
      )}
    </button>
  );
}
