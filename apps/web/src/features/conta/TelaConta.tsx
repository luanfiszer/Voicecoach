/**
 * Conta — o Perfil do mobile (CARD-050/051) + a cota do dia do artboard 12
 * (ADR-0064), que o mobile ainda não mostra.
 *
 * Excluir a conta pede confirmação em dois passos, com o MESMO texto do
 * mobile: é a única ação irreversível do produto (ADR-0069).
 */

import type { CotaDoDia } from '@voicecoach/api-client';
import { useEffect, useState } from 'react';

import { mensagemDeErro } from '@/features/auth/mensagensDeErro';
import { useClienteAutenticado, useSessao } from '@/features/auth/useSessao';
import estilosDaCasca from '@/features/casca/casca.module.css';
import estilos from '@/features/conta/conta.module.css';
import {
  fracaoUsada,
  mensagemDeBloqueio,
  rotuloDaVirada,
  rotuloDoSaldo,
} from '@/features/conta/rotulosDaCota';
import { Botao } from '@/ui/Botao';
import { LinkDeTexto } from '@/ui/LinkDeTexto';
import estilosDeUi from '@/ui/ui.module.css';

type EstadoDaCota =
  | { tipo: 'carregando' }
  | { tipo: 'pronta'; cota: CotaDoDia }
  | { tipo: 'falhou'; mensagem: string };

function CartaoDaCota() {
  const cliente = useClienteAutenticado();
  const [estado, setEstado] = useState<EstadoDaCota>({ tipo: 'carregando' });

  useEffect(() => {
    const controlador = new AbortController();
    cliente
      .lerCota(controlador.signal)
      .then((cota) => setEstado({ tipo: 'pronta', cota }))
      .catch((erro: unknown) => {
        if (!controlador.signal.aborted) {
          setEstado({ tipo: 'falhou', mensagem: mensagemDeErro(erro) });
        }
      });
    return () => controlador.abort();
  }, [cliente]);

  return (
    <article className={estilosDeUi.cartao} aria-busy={estado.tipo === 'carregando'}>
      <span className="rotulo">Fala de hoje</span>
      {estado.tipo === 'carregando' ? <p className="apoio">Carregando…</p> : null}
      {estado.tipo === 'falhou' ? <p className="erro">{estado.mensagem}</p> : null}
      {estado.tipo === 'pronta' ? (
        <>
          <div className={estilos.linha}>
            <span className={estilos.saldo}>{rotuloDoSaldo(estado.cota)}</span>
            <span className="apoio">{rotuloDaVirada(estado.cota.resets_at)}</span>
          </div>
          <div
            className={estilos.barra}
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(fracaoUsada(estado.cota) * 100)}
            aria-label="Minutos de fala usados hoje"
          >
            <div
              className={estilos.preenchimento}
              style={{ width: `${fracaoUsada(estado.cota) * 100}%` }}
            />
          </div>
          {mensagemDeBloqueio(estado.cota.blocked_reason) ? (
            <p className="erro">{mensagemDeBloqueio(estado.cota.blocked_reason)}</p>
          ) : null}
        </>
      ) : null}
    </article>
  );
}

function ExcluirConta() {
  const sessao = useSessao();
  const cliente = useClienteAutenticado();
  const [confirmando, setConfirmando] = useState(false);
  const [excluindo, setExcluindo] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const excluir = async () => {
    setErro(null);
    setExcluindo(true);
    try {
      await cliente.excluirConta();
      // A conta já não aceita nada no servidor; a limpeza local é a do logout.
      await sessao.sair();
    } catch (falha) {
      setExcluindo(false);
      setErro(mensagemDeErro(falha));
    }
  };

  if (!confirmando) {
    return (
      <div className={estilos.zonaDePerigo}>
        <LinkDeTexto
          rotulo="Excluir minha conta"
          aoClicar={() => setConfirmando(true)}
        />
      </div>
    );
  }

  return (
    <div
      className={estilos.zonaDePerigo}
      role="alertdialog"
      aria-labelledby="excluir-titulo"
    >
      <strong id="excluir-titulo">Isto não pode ser desfeito</strong>
      <p className="apoio">
        Suas gravações, transcrições e correções são apagadas. Você não consegue mais
        entrar com esta conta a partir de agora.
      </p>
      <p className="apoio">
        Se você tem uma assinatura ativa, excluir a conta <strong>não a cancela</strong>{' '}
        — cancele antes, onde você assinou.
      </p>
      {erro ? <p className="erro">{erro}</p> : null}
      <div className={estilos.botoes}>
        <Botao
          rotulo="Cancelar"
          variante="secundario"
          aoClicar={() => setConfirmando(false)}
          desabilitado={excluindo}
        />
        <Botao
          rotulo="Excluir definitivamente"
          variante="destrutivo"
          aoClicar={() => void excluir()}
          carregando={excluindo}
        />
      </div>
    </div>
  );
}

export function TelaConta() {
  const sessao = useSessao();
  return (
    <section className={estilosDaCasca.pagina}>
      <header className={estilosDaCasca.cabecalho}>
        <h1>Conta</h1>
        <p className="apoio">Seu saldo de fala e o acesso à conta.</p>
      </header>
      <CartaoDaCota />
      <div className={estilos.botoes}>
        <Botao
          rotulo="Sair"
          variante="secundario"
          aoClicar={() => void sessao.sair()}
        />
      </div>
      <ExcluirConta />
    </section>
  );
}
