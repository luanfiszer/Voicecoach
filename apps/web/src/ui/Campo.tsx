import { useId } from 'react';

import estilos from '@/ui/ui.module.css';

type Props = {
  rotulo: string;
  valor: string;
  aoMudar: (valor: string) => void;
  tipo?: 'text' | 'email' | 'password';
  /** Dica ao navegador/gerenciador de senhas — `current-password` ≠ `new-password`. */
  autocompletar?: string;
  erro?: string | null;
};

/** Rótulo + entrada + erro, ligados por `id` (o leitor de tela lê os três juntos). */
export function Campo({
  rotulo,
  valor,
  aoMudar,
  tipo = 'text',
  autocompletar,
  erro = null,
}: Props) {
  const id = useId();
  const idDoErro = `${id}-erro`;
  return (
    <div className={estilos.campo}>
      <label htmlFor={id} className="rotulo">
        {rotulo}
      </label>
      <input
        id={id}
        className={`${estilos.entrada} ${erro ? estilos.entradaComErro : ''}`}
        type={tipo}
        value={valor}
        onChange={(evento) => aoMudar(evento.target.value)}
        autoComplete={autocompletar}
        aria-invalid={erro !== null}
        aria-describedby={erro ? idDoErro : undefined}
      />
      {erro ? (
        <span id={idDoErro} className="erro">
          {erro}
        </span>
      ) : null}
    </div>
  );
}
