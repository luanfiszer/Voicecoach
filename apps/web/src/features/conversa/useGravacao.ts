/**
 * Gravar a fala no navegador (CARD-065) — o `useGravacao` do mobile sobre
 * `getUserMedia` + `MediaRecorder`.
 *
 * **Permissão é da plataforma, não do app** (regra da skill de cliente): o
 * estado vem de `navigator.permissions` quando o navegador o expõe, e o
 * pedido de verdade é o próprio `getUserMedia`. Negado no navegador não se
 * re-pergunta por código — a tela explica onde liberar (o cadeado da barra).
 *
 * **O limite de duração na web é por relógio**, diferente do mobile (que
 * reage a `durationMillis` do gravador nativo): o `MediaRecorder` não expõe
 * duração gravada. O relógio conta a partir do evento `start` do gravador —
 * o instante em que ele de fato começou —, não do clique.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { escolherFormato, tipoDoUpload } from '@/features/conversa/formatoDeGravacao';

export type Permissao = 'desconhecida' | 'concedida' | 'negada' | 'indisponivel';

export type FalaGravada = {
  audio: Blob;
  nomeDoArquivo: string;
  /** `Date.now()` do instante em que o gravador parou — o 1º marco do CARD-012. */
  pararEm: number;
};

export type Gravacao = {
  gravando: boolean;
  decorridos: number;
  limite: number;
  permissao: Permissao;
  /** A última gravação parou sozinha ao bater o limite. */
  pararaPorLimite: boolean;
  erro: string | null;
  iniciar: () => Promise<void>;
  parar: () => void;
};

function microfoneDisponivel(): boolean {
  return (
    typeof navigator !== 'undefined' &&
    navigator.mediaDevices?.getUserMedia !== undefined &&
    typeof MediaRecorder !== 'undefined'
  );
}

export function useGravacao(opcoes: {
  limiteSegundos: number;
  aoConcluir: (fala: FalaGravada) => void;
}): Gravacao {
  const [gravando, setGravando] = useState(false);
  const [decorridos, setDecorridos] = useState(0);
  const [permissao, setPermissao] = useState<Permissao>(
    microfoneDisponivel() ? 'desconhecida' : 'indisponivel',
  );
  const [pararaPorLimite, setPararaPorLimite] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const gravador = useRef<MediaRecorder | null>(null);
  const fluxo = useRef<MediaStream | null>(null);
  const relogio = useRef<ReturnType<typeof setInterval> | null>(null);
  const aoConcluir = useRef(opcoes.aoConcluir);
  aoConcluir.current = opcoes.aoConcluir;

  // O estado de permissão que o navegador já sabe, sem pedir nada.
  useEffect(() => {
    if (!microfoneDisponivel() || !navigator.permissions) return;
    let status: PermissionStatus | null = null;
    const atualizar = () => {
      if (!status) return;
      setPermissao(
        status.state === 'granted'
          ? 'concedida'
          : status.state === 'denied'
            ? 'negada'
            : 'desconhecida',
      );
    };
    navigator.permissions
      // `microphone` não está no tipo `PermissionName` do TS em todo navegador.
      .query({ name: 'microphone' as PermissionName })
      .then((s) => {
        status = s;
        atualizar();
        s.addEventListener('change', atualizar);
      })
      .catch(() => {
        // Firefox antigo/Safari: sem `query` para microfone — fica 'desconhecida'.
      });
    return () => status?.removeEventListener('change', atualizar);
  }, []);

  const pararRelogio = useCallback(() => {
    if (relogio.current !== null) clearInterval(relogio.current);
    relogio.current = null;
  }, []);

  /** Solta o microfone: desliga as trilhas (o indicador do navegador apaga). */
  const soltarMicrofone = useCallback(() => {
    for (const trilha of fluxo.current?.getTracks() ?? []) trilha.stop();
    fluxo.current = null;
  }, []);

  const parar = useCallback(() => {
    pararRelogio();
    if (gravador.current?.state === 'recording') gravador.current.stop();
  }, [pararRelogio]);

  const iniciar = useCallback(async () => {
    setErro(null);
    setPararaPorLimite(false);
    const formato = escolherFormato((t) => MediaRecorder.isTypeSupported(t));
    if (!microfoneDisponivel() || formato === null) {
      setPermissao('indisponivel');
      return;
    }

    let midia: MediaStream;
    try {
      midia = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (falha) {
      const negada =
        falha instanceof DOMException &&
        (falha.name === 'NotAllowedError' || falha.name === 'SecurityError');
      if (negada) setPermissao('negada');
      else setErro('Não encontramos um microfone neste computador.');
      return;
    }
    setPermissao('concedida');
    fluxo.current = midia;

    const pedacos: Blob[] = [];
    const novo = new MediaRecorder(midia, { mimeType: formato.mimeType });
    gravador.current = novo;
    let inicio = 0;

    novo.ondataavailable = (evento) => {
      if (evento.data.size > 0) pedacos.push(evento.data);
    };
    novo.onstart = () => {
      inicio = performance.now();
      setGravando(true);
      setDecorridos(0);
      relogio.current = setInterval(() => {
        const segundos = (performance.now() - inicio) / 1000;
        setDecorridos(segundos);
        if (segundos >= opcoes.limiteSegundos) {
          setPararaPorLimite(true);
          parar();
        }
      }, 200);
    };
    novo.onstop = () => {
      const pararEm = Date.now();
      pararRelogio();
      soltarMicrofone();
      setGravando(false);
      gravador.current = null;
      const tipo = tipoDoUpload(novo.mimeType, formato);
      const audio = new Blob(pedacos, { type: tipo });
      if (audio.size > 0) {
        aoConcluir.current({
          audio,
          nomeDoArquivo: `fala.${formato.extensao}`,
          pararEm,
        });
      }
    };
    novo.start();
  }, [opcoes.limiteSegundos, parar, pararRelogio, soltarMicrofone]);

  // Sair da tela gravando: para o gravador e apaga a luz do microfone.
  useEffect(
    () => () => {
      pararRelogio();
      if (gravador.current?.state === 'recording') {
        gravador.current.onstop = null;
        gravador.current.stop();
      }
      soltarMicrofone();
    },
    [pararRelogio, soltarMicrofone],
  );

  return {
    gravando,
    decorridos,
    limite: opcoes.limiteSegundos,
    permissao,
    pararaPorLimite,
    erro,
    iniciar,
    parar,
  };
}
