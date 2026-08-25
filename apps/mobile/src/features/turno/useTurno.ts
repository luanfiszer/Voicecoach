/**
 * A máquina de estados de um turn, do upload ao último trecho tocado.
 *
 * É o objetivo de aprendizado do CARD-012: async na UI de React Native com
 * `AbortController`, backoff, e o **caminho triste como cidadão de primeira
 * classe**. Três coisas aqui não têm paralelo no React web:
 *
 * 1. **O `AbortController` sobrevive à troca de tela.** Ele não é estado do
 *    componente: é o que cancela uma conexão HTTP viva. Por isso mora num
 *    `useRef` e é abortado em transições de máquina, não em `useEffect` de
 *    render.
 * 2. **`AppState` é um evento real.** Ir para background não é uma ficção de
 *    visibilidade como na web: o sistema pode congelar o JavaScript e derrubar a
 *    conexão. Voltar exige **reconectar com `Last-Event-ID`** (ADR-0041), e não
 *    "continuar de onde parou", que não existe.
 * 3. **A `Idempotency-Key` nasce ao PARAR DE GRAVAR**, não dentro do envio.
 *    Chave gerada por tentativa = turn duplicado por retry, que é exatamente o
 *    que o ADR-0042 existe para impedir.
 *
 * **Os dois caminhos de entrega são exercitados** (ADR-0026 item 4): SSE quando
 * `config.sseHabilitado`, `GET /v1/turns/{id}` com backoff quando não — ou
 * quando o stream falha. O recuo que ninguém testa apodrece.
 */

import {
  type Cliente,
  criarCliente,
  type EventoDoTurn,
  type Trecho,
  type Turn,
} from '@voicecoach/api-client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AppState, type AppStateStatus } from 'react-native';

import { config } from '@/config';
import { lerComoBlob } from '@/features/turno/arquivoLocal';
import { intervalos, MARCOS_VAZIOS, type Marcos } from '@/features/turno/marcos';
import {
  prepararParaTocar,
  useFilaDePlayback,
} from '@/features/turno/useFilaDePlayback';

export type EstadoDoTurn =
  | 'ocioso'
  | 'enviando'
  | 'transcrevendo'
  | 'ouvindo'
  | 'concluido'
  | 'falhou';

export type Correcao = {
  has_mistakes: boolean;
  original: string;
  corrected: string;
  tip: string;
};

export type Turno = {
  estado: EstadoDoTurn;
  turnId: string | null;
  transcricao: string | null;
  correcao: Correcao | null;
  /** Os trechos conhecidos, em ordem de `index`. */
  trechos: Trecho[];
  /** Qual trecho está tocando agora. */
  tocando: number | null;
  /** Gaps medidos entre trechos, em ms. */
  gaps: number[];
  /**
   * Índices já tocados até o fim.
   *
   * Existe porque **"o turn completou" e "o aluno terminou de ouvir" são
   * instantes diferentes**: o `completed` chega enquanto o primeiro trecho ainda
   * toca. Quem mede gap precisa esperar o segundo.
   */
  tocados: number[];
  marcos: Marcos;
  erro: string | null;
  /**
   * Falhou **depois** de o aluno já ter ouvido algo (ADR-0023 item 6).
   * A UI diz o que aconteceu **sem apagar o que já foi ouvido**.
   */
  entregaParcial: boolean;
  /** Por onde os eventos chegaram — o recuo precisa ser visível. */
  via: 'sse' | 'polling' | null;
  /**
   * O áudio não pôde ser tocado, mas **o texto continua** (ADR-0024 item 5).
   * Nunca é tela de erro fatal.
   */
  audioIndisponivel: boolean;
  enviar: (uri: string, pararEm: number) => Promise<void>;
  limpar: () => void;
};

/**
 * Chave de idempotência: única, não secreta.
 *
 * Não usa `crypto.randomUUID` porque ele não é garantido no runtime do Hermes e
 * a alternativa seria `expo-crypto` — dependência nova para gerar um
 * identificador que só precisa não colidir consigo mesmo (ADR-0044, régua alta).
 */
function novaChave(): string {
  const aleatorio = Math.random().toString(36).slice(2, 12);
  return `turn-${Date.now().toString(36)}-${aleatorio}`;
}

/**
 * O tipo do arquivo, derivado da extensão — **não fixo**.
 *
 * O servidor tem uma lista fechada e responde **415** ao que não está nela
 * (`api/audio_intake.py`). `audio/m4a` **não** está: o nome aceito é
 * `audio/x-m4a`. Foi assim que este mapa nasceu — com um 415 de verdade, num
 * upload de verdade, e não lendo a lista.
 */
function descreverArquivo(uri: string): { nome: string; tipo: string } {
  const extensao = uri.split('.').pop()?.toLowerCase() ?? '';
  const tipos: Record<string, string> = {
    m4a: 'audio/x-m4a',
    mp4: 'audio/mp4',
    aac: 'audio/aac',
    wav: 'audio/wav',
    mp3: 'audio/mpeg',
    ogg: 'audio/ogg',
    opus: 'audio/opus',
    webm: 'audio/webm',
  };
  // O default é o que o `expo-audio` grava no iOS com `HIGH_QUALITY`.
  const tipo = tipos[extensao] ?? 'audio/x-m4a';
  const sufixo = extensao in tipos ? extensao : 'm4a';
  return { nome: `fala.${sufixo}`, tipo };
}

/** Backoff do polling, em ms. Termina em 2 s: o turn saudável fecha em ~3 s. */
const BACKOFF_POLLING = [300, 400, 600, 900, 1200, 2000];

function ordenarPorIndice(trechos: Trecho[]): Trecho[] {
  // Ordenação NUMÉRICA (ADR-0023 item 2). Comparação de string poria
  // `chunk:10` antes de `chunk:2`.
  return [...trechos].sort((a, b) => a.index - b.index);
}

export function useTurno(): Turno {
  const cliente = useMemo<Cliente>(
    () => criarCliente({ baseUrl: config.apiBaseUrl }),
    [],
  );
  const turnAtualRef = useRef<string | null>(null);
  /** Índices para os quais a recuperação já foi tentada — uma vez cada. */
  const jaRecuperados = useRef(new Set<number>());

  /**
   * Um trecho não carregou. **URL assinada expirada é o caso esperado**
   * (ADR-0024 item 3: o TTL é curto de propósito), e o ADR-0024 item 5 diz o
   * que fazer, em ordem: repedir o `GET` para reassinar; se o trecho já não
   * existir mas o `full` sim, tocar o inteiro; se nenhum dos dois, áudio
   * indisponível com o **texto preservado** — nunca uma tela de erro fatal.
   */
  const recuperarAudio = useCallback(
    async (index: number) => {
      const id = turnAtualRef.current;
      if (!id || jaRecuperados.current.has(index)) return;
      jaRecuperados.current.add(index);

      try {
        const turn = await cliente.obterTurn(id);
        const fresco = (turn.chunks ?? []).find((c) => c.index === index);
        if (fresco) {
          filaRef.current?.renovar(fresco);
          return;
        }
        if (turn.reply_audio_url) {
          filaRef.current?.tocarInteiro(turn.reply_audio_url);
          return;
        }
        setAudioIndisponivel(true);
      } catch {
        setAudioIndisponivel(true);
      }
    },
    [cliente],
  );

  const fila = useFilaDePlayback({ aoTravar: (i) => void recuperarAudio(i) });
  const filaRef = useRef(fila);
  filaRef.current = fila;

  const [estado, setEstado] = useState<EstadoDoTurn>('ocioso');
  const [turnId, setTurnId] = useState<string | null>(null);
  const [transcricao, setTranscricao] = useState<string | null>(null);
  const [correcao, setCorrecao] = useState<Correcao | null>(null);
  const [trechos, setTrechos] = useState<Trecho[]>([]);
  const [marcos, setMarcos] = useState<Marcos>(MARCOS_VAZIOS);
  const [erro, setErro] = useState<string | null>(null);
  const [entregaParcial, setEntregaParcial] = useState(false);
  const [via, setVia] = useState<'sse' | 'polling' | null>(null);
  const [audioIndisponivel, setAudioIndisponivel] = useState(false);

  const abortador = useRef<AbortController | null>(null);
  const sessaoId = useRef<string | null>(null);
  /** Ids de evento já processados — a dedup do ADR-0041 item 3. */
  const idsVistos = useRef(new Set<string>());
  const ultimoEventoId = useRef<string | null>(null);
  const encerrado = useRef(false);

  const cancelar = useCallback(() => {
    abortador.current?.abort();
    abortador.current = null;
  }, []);

  const limpar = useCallback(() => {
    cancelar();
    fila.limpar();
    encerrado.current = false;
    idsVistos.current.clear();
    ultimoEventoId.current = null;
    turnAtualRef.current = null;
    setEstado('ocioso');
    setTurnId(null);
    setTranscricao(null);
    setCorrecao(null);
    setTrechos([]);
    setMarcos(MARCOS_VAZIOS);
    setErro(null);
    setEntregaParcial(false);
    setVia(null);
    setAudioIndisponivel(false);
    jaRecuperados.current.clear();
  }, [cancelar, fila]);

  const receberTrecho = useCallback(
    (trecho: Trecho) => {
      setMarcos((atual) =>
        atual.primeiroChunk === null ? { ...atual, primeiroChunk: Date.now() } : atual,
      );
      setTrechos((atual) =>
        atual.some((t) => t.index === trecho.index)
          ? atual
          : ordenarPorIndice([...atual, trecho]),
      );
      setEstado((atual) =>
        atual === 'concluido' || atual === 'falhou' ? atual : 'ouvindo',
      );
      // A fila descarta índice repetido por conta própria.
      fila.enfileirar(trecho);
    },
    [fila],
  );

  /** Aplica um evento do stream, ignorando o que já foi visto. */
  const aplicar = useCallback(
    (evento: EventoDoTurn) => {
      // **Dedup por id** (ADR-0041 item 3): o histórico da retomada e o canal ao
      // vivo podem entregar o mesmo evento. Sem isto, o aluno ouve a mesma frase
      // duas vezes — e o bug é intermitente.
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
          setCorrecao(evento.dados);
          break;
        case 'completed':
          encerrado.current = true;
          setEstado('concluido');
          break;
        case 'failed':
          encerrado.current = true;
          // **Não apaga o que já foi ouvido** (ADR-0023 item 6).
          setEntregaParcial(evento.dados.delivered_partially);
          setErro(evento.dados.reason);
          setEstado('falhou');
          break;
      }
    },
    [receberTrecho],
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
        for (const trecho of ordenarPorIndice(turn.chunks ?? [])) receberTrecho(trecho);

        if (turn.status === 'completed') {
          encerrado.current = true;
          setEstado('concluido');
          return;
        }
        if (turn.status === 'failed') {
          encerrado.current = true;
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
    [cliente, receberTrecho],
  );

  /** O caminho principal: SSE, com queda para o polling se ele não se sustentar. */
  const acompanhar = useCallback(
    async (id: string, sinal: AbortSignal) => {
      if (!config.sseHabilitado) {
        await pollar(id, sinal);
        return;
      }

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
        // O stream fechou sem `completed`/`failed` — timeout do servidor ou
        // queda de rede. O turn continua vivo no banco; o recuo o termina.
        if (!sinal.aborted && !encerrado.current) await pollar(id, sinal);
      } catch (falha) {
        if (sinal.aborted) return;
        // **O recuo não é tratamento de exceção decorativo**: é o contrato.
        await pollar(id, sinal);
        if (encerrado.current) return;
        setErro(falha instanceof Error ? falha.message : String(falha));
      }
    },
    [cliente, aplicar, pollar],
  );

  const enviar = useCallback(
    async (uri: string, pararEm: number) => {
      limpar();
      // A chave nasce AQUI, uma vez. O retry, lá dentro, reusa esta mesma.
      const chave = novaChave();
      const controlador = new AbortController();
      abortador.current = controlador;

      setEstado('enviando');
      setMarcos({ ...MARCOS_VAZIOS, parouDeFalar: pararEm });
      await prepararParaTocar();

      try {
        if (!sessaoId.current) {
          const sessao = await cliente.criarSessao(controlador.signal);
          sessaoId.current = sessao.id;
        }

        const arquivo = descreverArquivo(uri);
        const bytes = await lerComoBlob(uri, arquivo.tipo);
        const aceito = await cliente.enviarTurn({
          sessionId: sessaoId.current,
          audio: bytes,
          nomeDoArquivo: arquivo.nome,
          idempotencyKey: chave,
          sinal: controlador.signal,
        });

        setMarcos((atual) => ({ ...atual, uploadCompleto: Date.now() }));
        setTurnId(aceito.turn_id);
        turnAtualRef.current = aceito.turn_id;
        setEstado('transcrevendo');

        await acompanhar(aceito.turn_id, controlador.signal);
      } catch (falha) {
        if (controlador.signal.aborted) return;
        // `console.error` é permitido pelo Biome de propósito (ADR-0043): o
        // caminho triste tem de ser legível no log do Metro, ou depurar o app
        // vira leitura de captura de tela.
        console.error('[turno] falhou no envio:', falha);
        setErro(falha instanceof Error ? falha.message : String(falha));
        setEstado('falhou');
      }
    },
    [cliente, limpar, acompanhar],
  );

  // O primeiro instante audível vem da fila; ele é o quarto marco.
  useEffect(() => {
    if (fila.primeiroAudivelEm === null) return;
    setMarcos((atual) =>
      atual.primeiroAudivel === null
        ? { ...atual, primeiroAudivel: fila.primeiroAudivelEm }
        : atual,
    );
  }, [fila.primeiroAudivelEm]);

  /**
   * Voltar do background reconecta a partir do último evento recebido.
   *
   * **`Last-Event-ID` fora do esquema é 400**, não "comece do começo" (ADR-0041
   * item 4) — por isso o valor é sempre o último id REAL, ou nenhum. E o
   * `feedback` não volta na retomada (item 5): uma UI que o espere para sair do
   * carregamento trava para sempre, e é por isso que nada aqui depende dele.
   */
  useEffect(() => {
    const aoMudar = (situacao: AppStateStatus) => {
      const id = turnAtualRef.current;
      if (situacao !== 'active' || !id || encerrado.current) return;
      cancelar();
      const controlador = new AbortController();
      abortador.current = controlador;
      void acompanhar(id, controlador.signal);
    };
    const inscricao = AppState.addEventListener('change', aoMudar);
    return () => inscricao.remove();
  }, [acompanhar, cancelar]);

  useEffect(() => cancelar, [cancelar]);

  return {
    estado,
    turnId,
    transcricao,
    correcao,
    trechos,
    tocando: fila.tocando,
    gaps: fila.gaps,
    tocados: fila.concluidos,
    marcos,
    erro,
    entregaParcial,
    via,
    audioIndisponivel,
    enviar,
    limpar,
  };
}

export { intervalos };
