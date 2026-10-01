/** Configurações — o CARD-059 do mobile: limite de gravação (leitura) e versão. */

import { config } from '@/config';
import estilosDaCasca from '@/features/casca/casca.module.css';
import { rotuloDoLimiteDeGravacao } from '@/features/configuracoes/rotulosDeConfiguracoes';

export function TelaConfiguracoes() {
  return (
    <section className={estilosDaCasca.pagina}>
      <header className={estilosDaCasca.cabecalho}>
        <h1>Configurações</h1>
      </header>
      <div className={estilosDaCasca.secao}>
        <span className="rotulo">Limite de gravação</span>
        <p>{rotuloDoLimiteDeGravacao(config.limiteGravacaoSegundos)}</p>
        <p className="apoio">
          A gravação para sozinha ao chegar neste tempo — é por isso que uma fala longa
          às vezes é cortada.
        </p>
      </div>
      <div className={estilosDaCasca.secao}>
        <span className="rotulo">Tema</span>
        <p className="apoio">Segue o tema claro ou escuro do seu sistema.</p>
      </div>
      <div className={estilosDaCasca.secao}>
        <span className="rotulo">Sobre</span>
        <p>Voicecoach web · versão {config.versao}</p>
      </div>
    </section>
  );
}
