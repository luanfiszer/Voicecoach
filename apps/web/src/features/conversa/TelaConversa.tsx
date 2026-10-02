/**
 * Conversa — o artboard 01 na web (CARD-065): gravar, ouvir a resposta em
 * trechos, ler correções, traduzir. Os overlays cobrem os casos com ação
 * própria (microfone, cota, pausa, rede, travado — artboards 13–16).
 *
 * Clicar no botão de gravar no meio de uma resposta CALA o professor e
 * começa a nova fala — o mesmo comportamento do mobile (CARD-042).
 */

import { config } from '@/config';
import estilosDaCasca from '@/features/casca/casca.module.css';
import { BotaoGravar } from '@/features/conversa/BotaoGravar';
import estilos from '@/features/conversa/conversa.module.css';
import { corpoDaExcecao, TITULOS } from '@/features/conversa/excecoes';
import { ListaDoTurno } from '@/features/conversa/ListaDoTurno';
import { Overlay } from '@/features/conversa/Overlay';
import { formatarRelogio, subtitulo } from '@/features/conversa/rotulosDaConversa';
import { useGravacao } from '@/features/conversa/useGravacao';
import { useTurno } from '@/features/conversa/useTurno';
import { Botao } from '@/ui/Botao';

export function TelaConversa() {
  const turno = useTurno();
  const gravacao = useGravacao({
    limiteSegundos: config.limiteGravacaoSegundos,
    aoConcluir: (fala) => void turno.enviar(fala),
  });

  const ocupado = turno.estado === 'enviando' || turno.estado === 'transcrevendo';

  const alternar = () => {
    if (gravacao.gravando) {
      gravacao.parar();
      return;
    }
    turno.limpar(); // cala a resposta anterior antes de ouvir o aluno
    void gravacao.iniciar();
  };

  return (
    <section className={estilos.tela}>
      <header className={estilosDaCasca.cabecalho}>
        <h1>Sessão de hoje</h1>
        <p className="apoio">{subtitulo(gravacao.gravando, turno.estado)}</p>
      </header>

      <ListaDoTurno turno={turno} />

      {gravacao.pararaPorLimite ? (
        <p className="erro">
          Chegamos ao limite de {formatarRelogio(gravacao.limite)} — sua fala foi
          guardada até aqui.
        </p>
      ) : null}
      {gravacao.erro ? <p className="erro">{gravacao.erro}</p> : null}

      <div className={estilos.rodape}>
        {gravacao.gravando ? (
          <span className="apoio" aria-live="off">
            {formatarRelogio(gravacao.decorridos)} / {formatarRelogio(gravacao.limite)}
          </span>
        ) : null}
        <BotaoGravar
          gravando={gravacao.gravando}
          desabilitado={ocupado || gravacao.permissao === 'indisponivel'}
          aoClicar={alternar}
        />
        {gravacao.permissao === 'indisponivel' ? (
          <p className="apoio">
            Este navegador não grava áudio. Use o Chrome, o Firefox ou o Safari
            atualizados.
          </p>
        ) : null}
      </div>

      {gravacao.permissao === 'negada' ? (
        <Overlay titulo="Precisamos do microfone">
          <p className="apoio">
            O navegador bloqueou o microfone para este site. Clique no cadeado ao lado
            do endereço, permita o microfone e recarregue a página.
          </p>
          <Botao
            rotulo="Já liberei — recarregar"
            aoClicar={() => window.location.reload()}
          />
        </Overlay>
      ) : null}

      {turno.excecao ? (
        <Overlay titulo={TITULOS[turno.excecao.tipo]}>
          <p className="apoio">{corpoDaExcecao(turno.excecao)}</p>
          {turno.excecao.tipo === 'offline' ? (
            <Botao rotulo="Tentar enviar de novo" aoClicar={turno.tentarNovamente} />
          ) : null}
          {turno.excecao.tipo === 'travado' ? (
            <>
              <Botao rotulo="Continuar esperando" aoClicar={turno.dispensarExcecao} />
              <Botao
                rotulo="Descartar"
                variante="secundario"
                aoClicar={() => void turno.descartar()}
              />
            </>
          ) : (
            <Botao
              rotulo="Entendi"
              variante="secundario"
              aoClicar={turno.dispensarExcecao}
            />
          )}
        </Overlay>
      ) : null}
    </section>
  );
}
