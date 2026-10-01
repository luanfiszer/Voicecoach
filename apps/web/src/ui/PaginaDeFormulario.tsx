import type { FormEvent, ReactNode } from 'react';

import estilos from '@/ui/ui.module.css';

type Props = {
  titulo: string;
  subtitulo?: ReactNode;
  /** Presente = a coluna é um `<form>` e o Enter envia. */
  aoEnviar?: () => void;
  children: ReactNode;
};

/** A coluna centrada das telas de auth — o mesmo esqueleto das telas do mobile. */
export function PaginaDeFormulario({ titulo, subtitulo, aoEnviar, children }: Props) {
  const conteudo = (
    <>
      <h1>{titulo}</h1>
      {subtitulo ? <p className="apoio">{subtitulo}</p> : null}
      {children}
    </>
  );
  return (
    <main className={estilos.paginaDeFormulario}>
      {aoEnviar ? (
        <form
          className={estilos.formulario}
          onSubmit={(evento: FormEvent) => {
            evento.preventDefault();
            aoEnviar();
          }}
          noValidate
        >
          {conteudo}
        </form>
      ) : (
        <div className={estilos.formulario}>{conteudo}</div>
      )}
    </main>
  );
}
