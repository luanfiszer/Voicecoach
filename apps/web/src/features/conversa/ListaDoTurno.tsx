/**
 * A cascata na tela, **na ordem em que ela acontece** (ADR-0022/0023): a fala
 * do aluno, o ÁUDIO do professor em trechos, e as correções por último. O
 * design (artboard 05) é anterior à cascata e desenha a ordem invertida — a
 * divergência está em `docs/design/README.md`.
 */

import estilos from '@/features/conversa/conversa.module.css';
import {
  mensagemDeRecusa,
  rotuloDaSeveridade,
  rotuloDoBotaoDeTraduzir,
  rotuloDoTipo,
} from '@/features/conversa/rotulosDaConversa';
import type { Turno } from '@/features/conversa/useTurno';

export function ListaDoTurno({ turno }: { turno: Turno }) {
  if (turno.estado === 'ocioso') return null;

  return (
    <div className={estilos.lista} aria-live="polite">
      {turno.transcricao ? (
        <div className={estilos.bolha}>
          <span className="rotulo">Você disse</span>
          <p>{turno.transcricao}</p>
        </div>
      ) : (
        <p className="apoio">
          {turno.estado === 'enviando' ? 'Enviando sua fala…' : 'Transcrevendo…'}
        </p>
      )}

      {turno.recusa ? (
        <div className={`${estilos.bolha} ${estilos.recusa}`}>
          <span className="rotulo">Professor</span>
          <p>{mensagemDeRecusa(turno.recusa)}</p>
        </div>
      ) : null}

      {turno.trechos.length > 0 ? (
        <div className={estilos.bolha}>
          <span className="rotulo">Professor</span>
          {turno.trechos.map((trecho) => (
            <p
              key={trecho.index}
              className={
                turno.fila.tocando === trecho.index ? estilos.trechoTocando : ''
              }
            >
              {trecho.text}
            </p>
          ))}
          {turno.estado === 'concluido' ? (
            turno.traducao.fase === 'traduzido' && turno.traducao.texto ? (
              <p className="apoio">{turno.traducao.texto}</p>
            ) : (
              <button
                type="button"
                className={estilos.botaoDeTexto}
                disabled={turno.traducao.fase === 'traduzindo'}
                onClick={() => void turno.traduzir()}
              >
                {rotuloDoBotaoDeTraduzir(turno.traducao.fase)}
              </button>
            )
          ) : null}
        </div>
      ) : null}

      {turno.correcoes.map((correcao) => (
        <div key={correcao.index} className={`${estilos.bolha} ${estilos.correcao}`}>
          <div className={estilos.selos}>
            <span className={`rotulo ${estilos.seloDoTipo}`}>
              {rotuloDoTipo(correcao.tipo)}
            </span>
            <span className="rotulo">{rotuloDaSeveridade(correcao.severidade)}</span>
          </div>
          <span className={estilos.original}>{correcao.original}</span>
          <span className={estilos.corrigido}>{correcao.corrigido}</span>
          <p className="apoio">{correcao.explicacao}</p>
        </div>
      ))}

      {turno.audioIndisponivel ? (
        <div className={estilos.bolha}>
          <span className="rotulo">Sem áudio agora</span>
          <p className="apoio">
            O áudio desta resposta não está mais disponível. O texto continua aqui.
          </p>
        </div>
      ) : null}

      {turno.erro && !turno.excecao ? (
        <div className={estilos.bolha}>
          <span className="rotulo">
            {turno.entregaParcial ? 'A resposta ficou pela metade' : 'Não deu certo'}
          </span>
          <p className="apoio">
            {turno.entregaParcial
              ? 'O que você já ouviu continua aqui. O resto não chegou.'
              : turno.erro}
          </p>
        </div>
      ) : null}
    </div>
  );
}
