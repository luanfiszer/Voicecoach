/**
 * A máquina de estados de um turn na web (CARD-065) — o `useTurno` do mobile
 * (CARD-012/016/027/032/058), com três diferenças:
 *
 * 1. **Sem `AppState`.** No iOS, ir para background congela o JavaScript e
 *    derruba a conexão; uma aba do navegador em segundo plano continua viva.
 *    O recuo para polling (ADR-0026) cobre a queda real de rede.
 * 2. **`rejected` é tratado** (CARD-040): o turn terminou sem professor e o
 *    aluno vê o convite a repetir. O mobile ainda ignora esse evento.
 * 3. **A fila toca `HTMLAudioElement`** (`filaDePlayback.ts`).
 *
 * O que NÃO muda: a `Idempotency-Key` nasce uma vez por gravação (ADR-0042);
 * dedup de evento por id (ADR-0041); a falha não apaga o que já foi ouvido
 * (ADR-0023 item 6); áudio indisponível nunca é erro fatal (ADR-0024 item 5).
 */

import type { EventoDoTurn, Trecho, Turn } from '@voicecoach/api-client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { useClienteAutenticado } from '@/features/auth/useSessao';
import { type Excecao, excecaoDoErro } from '@/features/conversa/excecoes';
import {
  criarFila,
  ESTADO_VAZIO,
  type EstadoDaFila,
} from '@/features/conversa/filaDePlayback';
import type {
  EstadoDaConversa,
  FaseDaTraducao,
  MotivoDeRecusa,
  Severidade,
  TipoDeCorrecao,
} from '@/features/conversa/rotulosDaConversa';
import type { FalaGravada } from '@/features/conversa/useGravacao';

export type Correcao = {
  index: number;
  tipo: TipoDeCorrecao;
  original: string;
  corrigido: string;
  explicacao: string;
  severidade: Severidade;
};

export type Turno = {
  estado: EstadoDaConversa;
  transcricao: string | null;
  trechos: Trecho[];
  correcoes: Correcao[];
  fila: EstadoDaFila;
  recusa: MotivoDeRecusa | null;
  erro: string | null;
  entregaParcial: boolean;
  audioIndisponivel: boolean;
  excecao: Excecao | null;
  traducao: { fase: FaseDaTraducao; texto: string | null };
  /** Por onde os eventos chegaram — o recuo precisa ser visível no log. */
  via: 'sse' | 'polling' | null;
  enviar: (fala: FalaGravada) => Promise<void>;
  tentarNovamente: () => void;
  traduzir: () => Promise<void>;
  descartar: () => Promise<void>;
  limpar: () => void;
  dispensarExcecao: () => void;
};

/** "Sua fala foi enviada, mas a resposta não chegou em 30 s" (artboard 16). */
const RESPOSTA_TRAVADA_EM_SEGUNDOS = 30;
const BACKOFF_POLLING = [300, 400, 600, 900, 1200, 2000];

function mapearCorrecoes(payload: Turn['corrections'] | undefined): Correcao[] {
  return (payload ?? []).map((c) => ({
    index: c.index,
    tipo: c.type,
    original: c.original_excerpt,
    corrigido: c.corrected_form,
    explicacao: c.explanation,
    severidade: c.severity,
  }));
}

function ordenar(trechos: Trecho[]): Trecho[] {
  return [...trechos].sort((a, b) => a.index - b.index);
}

export function useTurno(): Turno {
  const cliente = useClienteAutenticado();

  const [estado, setEstado] = useState<EstadoDaConversa>('ocioso');
  const [transcricao, setTranscricao] = useState<string | null>(null);
  const [trechos, setTrechos] = useState<Trecho[]>([]);
  const [correcoes, setCorrecoes] = useState<Correcao[]>([]);
  const [estadoDaFila, setEstadoDaFila] = useState<EstadoDaFila>(ESTADO_VAZIO);
  const [recusa, setRecusa] = useState<MotivoDeRecusa | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [entregaParcial, setEntregaParcial] = useState(false);
  const [audioIndisponivel, setAudioIndisponivel] = useState(false);
  const [excecao, setExcecao] = useState<Excecao | null>(null);
  const [traducao, setTraducao] = useState<Turno['traducao']>({
    fase: 'ocioso',
    texto: null,
  });
  const [via, setVia] = useState<'sse' | 'polling' | null>(null);

  const turnAtual = useRef<string | null>(null);
  const sessaoId = useRef<string | null>(null);
  const abortador = useRef<AbortController | null>(null);
  const idsVistos = useRef(new Set<string>());
  const ultimoEventoId = useRef<string | null>(null);
  const encerrado = useRef(false);
  const ultimaFala = useRef<FalaGravada | null>(null);
  const travamento = useRef<ReturnType<typeof setTimeout> | null>(null);
  const jaRecuperados = useRef(new Set<number>());
  const marcos = useRef<{ parou: number; upload: number | null }>({
    parou: 0,
    upload: null,
  });

  // A fila nasce uma vez. Ela avisa "travou" por um ref, porque quem trata
  // (`recuperarAudio`) precisa da própria fila — o ref quebra o ciclo.
  const aoTravarRef = useRef<(index: number) => void>(() => {});
  const fila = useMemo(
    () =>
      criarFila({
        criarAudio: () => new Audio(),
        agora: () => Date.now(),
        agendar: (fn, ms) => {
          const t = setTimeout(fn, ms);
          return () => clearTimeout(t);
        },
        aoMudar: setEstadoDaFila,
        aoTravar: (i) => aoTravarRef.current(i),
      }),
    [],
  );

  /**
   * Trecho que não ficou audível: URL assinada vencida é o caso esperado
   * (ADR-0024 item 5). Repede o turn para reassinar; sem trecho, toca o
   * inteiro; sem nenhum dos dois, "sem áudio" com o texto preservado.
   */
  const recuperarAudio = useCallback(
    async (index: number) => {
      const id = turnAtual.current;
      if (!id || jaRecuperados.current.has(index)) return;
      jaRecuperados.current.add(index);
      try {
        const turn = await cliente.obterTurn(id);
        if (turnAtual.current !== id) return; // o aluno já gravou outro
        const fresco = (turn.chunks ?? []).find((c) => c.index === index);
        if (fresco) {
          fila.renovar({ index, url: fresco.url });
          return;
        }
        if (turn.reply_audio_url) {
          fila.tocarInteiro(turn.reply_audio_url);
          return;
        }
        setAudioIndisponivel(true);
      } catch {
        setAudioIndisponivel(true);
      }
    },
    [cliente, fila],
  );

  aoTravarRef.current = (i) => void recuperarAudio(i);

  const desarmarTravamento = useCallback(() => {
    if (travamento.current !== null) clearTimeout(travamento.current);
    travamento.current = null;
  }, []);

  const limpar = useCallback(() => {
    abortador.current?.abort();
    abortador.current = null;
    desarmarTravamento();
    fila.limpar();
    encerrado.current = false;
    idsVistos.current.clear();
    ultimoEventoId.current = null;
    turnAtual.current = null;
    jaRecuperados.current.clear();
    setEstado('ocioso');
    setTranscricao(null);
    setTrechos([]);
    setCorrecoes([]);
    setRecusa(null);
    setErro(null);
    setEntregaParcial(false);
    setAudioIndisponivel(false);
    setExcecao(null);
    setTraducao({ fase: 'ocioso', texto: null });
    setVia(null);
  }, [desarmarTravamento, fila]);

  const receberTrecho = useCallback(
    (trecho: Trecho) => {
      setTrechos((atual) =>
        atual.some((t) => t.index === trecho.index)
          ? atual
          : ordenar([...atual, trecho]),
      );
      setEstado((atual) =>
        atual === 'concluido' || atual === 'falhou' ? atual : 'ouvindo',
      );
      fila.enfileirar({ index: trecho.index, url: trecho.url });
    },
    [fila],
  );

  const encerrar = useCallback(() => {
    encerrado.current = true;
    desarmarTravamento();
    setExcecao(null);
  }, [desarmarTravamento]);

  const aplicar = useCallback(
    (evento: EventoDoTurn) => {
      if (idsVistos.current.has(evento.id)) return;
      idsVistos.current.add(evento.id);
      ultimoEventoId.current = evento.id;

      switch (evento.tipo) {
        case 'transcribed':
          setTranscricao(evento.dados.transcript);
          setEstado((atual) => (atual === 'enviando' ? 'transcrevendo' : atual));
          break;
        case 'chunk':
          receberTrecho(evento.dados);
          break;
        case 'feedback':
          setCorrecoes(mapearCorrecoes(evento.dados.corrections));
          break;
        case 'completed':
          encerrar();
          setEstado('concluido');
          break;
        case 'rejected':
          encerrar();
          setRecusa(evento.dados.reason);
          setEstado('recusado');
          break;
        case 'failed':
          encerrar();
          setEntregaParcial(evento.dados.delivered_partially);
          setErro(evento.dados.reason);
          setEstado('falhou');
          break;
      }
    },
    [receberTrecho, encerrar],
  );

  /** O contrato de recuo: `GET /v1/turns/{id}` com backoff (ADR-0026 item 4). */
  const pollar = useCallback(
    async (id: string, sinal: AbortSignal) => {
      setVia('polling');
      for (let passo = 0; !sinal.aborted && !encerrado.current; passo++) {
        let turn: Turn;
        try {
          turn = await cliente.obterTurn(id, sinal);
        } catch (falha) {
          if (sinal.aborted) return;
          setErro(falha instanceof Error ? falha.message : String(falha));
          setEstado('falhou');
          return;
        }
        if (turn.transcript) setTranscricao(turn.transcript);
        for (const trecho of ordenar(turn.chunks ?? [])) receberTrecho(trecho);
        setCorrecoes(mapearCorrecoes(turn.corrections));

        if (turn.rejection_reason) {
          encerrar();
          setRecusa(turn.rejection_reason);
          setEstado('recusado');
          return;
        }
        if (turn.status === 'completed') {
          encerrar();
          setEstado('concluido');
          return;
        }
        if (turn.status === 'failed') {
          encerrar();
          setEntregaParcial(turn.delivered_partially);
          setErro(turn.failure_reason ?? 'o turn falhou');
          setEstado('falhou');
          return;
        }
        const espera =
          BACKOFF_POLLING[Math.min(passo, BACKOFF_POLLING.length - 1)] ?? 2000;
        await new Promise((r) => setTimeout(r, espera));
      }
    },
    [cliente, receberTrecho, encerrar],
  );

  /** SSE primeiro; o recuo termina o turn se o stream não se sustentar. */
  const acompanhar = useCallback(
    async (id: string, sinal: AbortSignal) => {
      try {
        setVia('sse');
        for await (const evento of cliente.acompanharTurn(id, {
          sinal,
          ultimoEventoId: ultimoEventoId.current,
        })) {
          if (sinal.aborted) return;
          aplicar(evento);
          if (encerrado.current) return;
        }
        if (!sinal.aborted && !encerrado.current) await pollar(id, sinal);
      } catch {
        if (sinal.aborted) return;
        await pollar(id, sinal);
      }
    },
    [cliente, aplicar, pollar],
  );

  const enviar = useCallback(
    async (fala: FalaGravada) => {
      ultimaFala.current = fala;
      limpar();
      // A chave nasce AQUI, uma vez por gravação; o retry interno a reusa.
      const chave = `turn-${Date.now().toString(36)}-${crypto.randomUUID()}`;
      const controlador = new AbortController();
      abortador.current = controlador;
      marcos.current = { parou: fala.pararEm, upload: null };
      setEstado('enviando');

      try {
        if (!sessaoId.current) {
          sessaoId.current = (await cliente.criarSessao(controlador.signal)).id;
        }
        const aceito = await cliente.enviarTurn({
          sessionId: sessaoId.current,
          audio: fala.audio,
          nomeDoArquivo: fala.nomeDoArquivo,
          idempotencyKey: chave,
          sinal: controlador.signal,
        });
        marcos.current.upload = Date.now();
        turnAtual.current = aceito.turn_id;
        setEstado('transcrevendo');
        travamento.current = setTimeout(() => {
          if (!encerrado.current) {
            setExcecao({ tipo: 'travado', segundos: RESPOSTA_TRAVADA_EM_SEGUNDOS });
          }
        }, RESPOSTA_TRAVADA_EM_SEGUNDOS * 1000);
        await acompanhar(aceito.turn_id, controlador.signal);
      } catch (falha) {
        if (controlador.signal.aborted) return;
        console.error('[conversa] falhou no envio:', falha);
        setErro(falha instanceof Error ? falha.message : String(falha));
        setEstado('falhou');
        setExcecao(excecaoDoErro(falha));
      }
    },
    [cliente, limpar, acompanhar],
  );

  const tentarNovamente = useCallback(() => {
    if (ultimaFala.current) void enviar(ultimaFala.current);
  }, [enviar]);

  /** O botão `traduzir` (CARD-058): uma vez por resposta (RNF6 do CARD-036). */
  const traduzir = useCallback(async () => {
    const id = turnAtual.current;
    if (!id || traducao.fase === 'traduzido' || traducao.fase === 'traduzindo') return;
    setTraducao({ fase: 'traduzindo', texto: null });
    try {
      const resultado = await cliente.traduzirTexto(id, 'reply');
      setTraducao({ fase: 'traduzido', texto: resultado.text });
    } catch {
      setTraducao({ fase: 'falhou', texto: null });
    }
  }, [cliente, traducao.fase]);

  /** "Descartar" (CARD-032): marca no servidor e destrava a tela. */
  const descartar = useCallback(async () => {
    const id = turnAtual.current;
    if (id) {
      try {
        await cliente.descartarTurn(id);
      } catch (falha) {
        console.error('[conversa] descartar falhou:', falha);
      }
    }
    limpar();
  }, [cliente, limpar]);

  // O número do produto (CARD-012): do clique de parar ao primeiro som.
  useEffect(() => {
    if (estadoDaFila.primeiroAudivelEm === null) return;
    const { parou, upload } = marcos.current;
    console.info(
      `[conversa] upload ${upload === null ? '—' : upload - parou}ms · ` +
        `primeiro som ${estadoDaFila.primeiroAudivelEm - parou}ms · via ${via}`,
    );
  }, [estadoDaFila.primeiroAudivelEm, via]);

  useEffect(() => {
    if (estadoDaFila.gaps.length === 0) return;
    console.info(`[conversa] gaps entre trechos: [${estadoDaFila.gaps.join(', ')}] ms`);
  }, [estadoDaFila.gaps]);

  // Sair da tela: cancela a conexão e CALA o áudio (LEARNING-0006).
  useEffect(
    () => () => {
      abortador.current?.abort();
      desarmarTravamento();
      fila.limpar();
    },
    [desarmarTravamento, fila],
  );

  return {
    estado,
    transcricao,
    trechos,
    correcoes,
    fila: estadoDaFila,
    recusa,
    erro,
    entregaParcial,
    audioIndisponivel,
    excecao,
    traducao,
    via,
    enviar,
    tentarNovamente,
    traduzir,
    descartar,
    limpar,
    dispensarExcecao: () => setExcecao(null),
  };
}
