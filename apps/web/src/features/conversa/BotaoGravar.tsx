import estilos from '@/features/conversa/conversa.module.css';

type Props = {
  gravando: boolean;
  desabilitado: boolean;
  aoClicar: () => void;
};

/**
 * O botão de gravar do style guide: 84px, círculo para falar, quadrado para
 * parar, pulso enquanto grava. `aria-pressed` diz ao leitor de tela o que o
 * pulso diz aos olhos.
 */
export function BotaoGravar({ gravando, desabilitado, aoClicar }: Props) {
  return (
    <button
      type="button"
      className={`${estilos.gravar} ${gravando ? estilos.gravando : ''}`}
      onClick={aoClicar}
      disabled={desabilitado}
      aria-pressed={gravando}
      aria-label={gravando ? 'Parar e enviar' : 'Gravar'}
    >
      <span className={estilos.icone} aria-hidden="true" />
    </button>
  );
}
