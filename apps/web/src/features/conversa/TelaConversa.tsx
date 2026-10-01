/**
 * Conversa — o lugar da fase 2 (CARD-065). A conversa por áudio no navegador
 * (gravação, entrega em trechos, correções) chega lá; aqui só o aviso, para a
 * aba existir com o lugar certo desde já.
 */

import estilosDaCasca from '@/features/casca/casca.module.css';

export function TelaConversa() {
  return (
    <section className={estilosDaCasca.pagina}>
      <header className={estilosDaCasca.cabecalho}>
        <h1>Conversa</h1>
        <p className="apoio">
          A conversa por áudio na web está a caminho. Por enquanto, pratique pelo app no
          celular — suas sessões aparecem no Histórico daqui.
        </p>
      </header>
    </section>
  );
}
