/**
 * Histórico — o artboard 10 (CARD-029/030), na web.
 *
 * Mesmos dados e textos do mobile: data, duração falada, correções, turnos e
 * o aviso de áudio expirado. Abrir uma sessão e rever a conversa ainda não
 * existe: o backend não tem a leitura de uma sessão com os turns (gatilho
 * registrado no CARD-064).
 */

import type { SessaoDoHistorico } from '@voicecoach/api-client';

import estilosDaCasca from '@/features/casca/casca.module.css';
import estilos from '@/features/historico/historico.module.css';
import {
  AVISO_DE_AUDIO_EXPIRADO,
  cabecalhoDaSessao,
  formatarDuracao,
  NOTA_DA_JANELA,
  rotuloDeCorrecoes,
  rotuloDeTurnos,
} from '@/features/historico/rotulosDoHistorico';
import { useHistorico } from '@/features/historico/useHistorico';
import { LinkDeTexto } from '@/ui/LinkDeTexto';
import estilosDeUi from '@/ui/ui.module.css';

function CartaoDaSessao({ sessao, agora }: { sessao: SessaoDoHistorico; agora: Date }) {
  return (
    <article className={estilosDeUi.cartao}>
      <div className={estilos.linhaDoTopo}>
        <span className={estilos.titulo}>
          {cabecalhoDaSessao(sessao.started_at, agora)}
        </span>
        <span className="apoio">{formatarDuracao(sessao.spoken_seconds)}</span>
      </div>
      <div className={estilos.chips}>
        <span className={`${estilos.chip} ${estilos.chipDeCorrecao}`}>
          {rotuloDeCorrecoes(sessao.corrections)}
        </span>
        <span className={estilos.chip}>{rotuloDeTurnos(sessao.turns)}</span>
      </div>
      {sessao.reply_media_available ? null : (
        <p className={`apoio ${estilos.aviso}`}>ⓘ {AVISO_DE_AUDIO_EXPIRADO}</p>
      )}
    </article>
  );
}

export function TelaHistorico() {
  const { estado, recarregar } = useHistorico();
  // Um só `Date` por render: "Hoje"/"Ontem" não podem divergir entre cartões.
  const agora = new Date();

  return (
    <section className={estilosDaCasca.pagina}>
      <header className={estilosDaCasca.cabecalho}>
        <h1>Histórico</h1>
        <p className="apoio">Suas conversas, com o tempo falado e as correções.</p>
      </header>

      <div className={estilos.acoes}>
        <LinkDeTexto rotulo="Atualizar" aoClicar={recarregar} />
      </div>

      {estado.tipo === 'carregando' ? <p className="apoio">Carregando…</p> : null}
      {estado.tipo === 'falhou' ? <p className="erro">{estado.mensagem}</p> : null}
      {estado.tipo === 'vazio' ? (
        <p className="apoio">
          Nenhuma sessão ainda. Sua primeira conversa aparece aqui.
        </p>
      ) : null}
      {estado.tipo === 'pronto' ? (
        <>
          {estado.sessoes.map((sessao) => (
            <CartaoDaSessao key={sessao.id} sessao={sessao} agora={agora} />
          ))}
          <p className={`apoio ${estilos.nota}`}>{NOTA_DA_JANELA}</p>
        </>
      ) : null}
    </section>
  );
}
