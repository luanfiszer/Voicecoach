import estilos from '@/ui/ui.module.css';

/** Ação secundária que parece link — é `<button>` porque não navega por URL. */
export function LinkDeTexto({
  rotulo,
  aoClicar,
}: {
  rotulo: string;
  aoClicar: () => void;
}) {
  return (
    <button type="button" className={estilos.link} onClick={aoClicar}>
      {rotulo}
    </button>
  );
}
