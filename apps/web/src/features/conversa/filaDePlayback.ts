/**
 * A fila de playback da web (CARD-065): N trechos tocados em sequência, sem
 * buraco audível — a `useFilaDePlayback` do mobile (ADR-0047), sobre
 * `HTMLAudioElement` em vez do `expo-audio`.
 *
 * **As mesmas três regras do mobile, pelo mesmo motivo:**
 * 1. **Um elemento de áudio POR TRECHO, criado na chegada** — o download do
 *    trecho N+1 acontece enquanto o N toca (prefetch), em vez de cair dentro
 *    do intervalo entre os dois.
 * 2. **A ordem é o `index`, nunca a de chegada** (ADR-0023 item 2); o trecho 1
 *    que chega antes do 0 espera.
 * 3. **Dedup por índice** (ADR-0041 item 3): histórico da retomada e canal ao
 *    vivo podem entregar o mesmo trecho; tocar duas vezes é o modo de falha.
 *
 * **Soltar não é desligar, aqui também** (LEARNING-0006): um `<audio>` fora
 * da árvore continua tocando até alguém pausá-lo. `liberar` faz `pause()`,
 * tira o `src` e chama `load()` — o jeito que a especificação HTML dá para
 * abortar o download e soltar o decodificador.
 *
 * Sem DOM: o elemento, o relógio e o timer entram por parâmetro, e é isso que
 * deixa o teste rodar em Node com elementos de mentira.
 */

/** O mínimo do `HTMLAudioElement` que a fila usa. */
export type AudioDaFila = {
  src: string;
  preload: string;
  play(): Promise<void>;
  pause(): void;
  load(): void;
  removeAttribute(nome: string): void;
  addEventListener(tipo: 'playing' | 'ended' | 'error', ouvinte: () => void): void;
};

export type TrechoDaFila = { index: number; url: string };

export type EstadoDaFila = {
  tocando: number | null;
  concluidos: number[];
  /** Do `ended` do trecho N ao `playing` do N+1, em ms. */
  gaps: number[];
  /** O instante em que o primeiro trecho ficou audível (o 4º marco do CARD-012). */
  primeiroAudivelEm: number | null;
};

export type Fila = {
  enfileirar(trecho: TrechoDaFila): void;
  /** Troca a URL de um trecho que não carregou (assinatura vencida) e tenta de novo. */
  renovar(trecho: TrechoDaFila): void;
  /** Abandona os trechos e toca o áudio inteiro — o recuo do ADR-0024 item 5. */
  tocarInteiro(url: string): void;
  limpar(): void;
  estado(): EstadoDaFila;
};

export const ESTADO_VAZIO: EstadoDaFila = {
  tocando: null,
  concluidos: [],
  gaps: [],
  primeiroAudivelEm: null,
};

/**
 * Quanto se espera um trecho ficar audível antes de chamá-lo de travado —
 * o mesmo prazo do mobile. URL assinada vencida dá 403, e o sintoma num
 * `<audio>` pode ser só silêncio.
 */
export const PRAZO_DE_CARGA_MS = 4000;

export function criarFila(opcoes: {
  criarAudio: () => AudioDaFila;
  agora: () => number;
  agendar: (fn: () => void, ms: number) => () => void;
  aoMudar: (estado: EstadoDaFila) => void;
  aoTravar: (index: number) => void;
  prazoMs?: number;
}): Fila {
  const prazo = opcoes.prazoMs ?? PRAZO_DE_CARGA_MS;
  const players = new Map<number, AudioDaFila>();
  const vistos = new Set<number>();
  let inteiro: AudioDaFila | null = null;
  let proximo = 0;
  let fimDoAnterior: number | null = null;
  let cancelarVigia: (() => void) | null = null;
  // Cada `limpar` muda a geração: ouvintes de elementos antigos ficam mudos
  // mesmo que o navegador ainda dispare um evento atrasado deles.
  let geracao = 0;
  let estado: EstadoDaFila = ESTADO_VAZIO;

  function publicar(parcial: Partial<EstadoDaFila>): void {
    estado = { ...estado, ...parcial };
    opcoes.aoMudar(estado);
  }

  function liberar(audio: AudioDaFila): void {
    audio.pause();
    audio.removeAttribute('src');
    audio.load();
  }

  function desarmarVigia(): void {
    cancelarVigia?.();
    cancelarVigia = null;
  }

  function aoFicarAudivel(index: number): void {
    desarmarVigia();
    const instante = opcoes.agora();
    publicar({
      tocando: index,
      primeiroAudivelEm: estado.primeiroAudivelEm ?? instante,
      gaps:
        fimDoAnterior === null
          ? estado.gaps
          : [...estado.gaps, Math.round(instante - fimDoAnterior)],
    });
    fimDoAnterior = null;
  }

  function aoTerminar(index: number): void {
    fimDoAnterior = opcoes.agora();
    proximo = index + 1;
    publicar({ tocando: null, concluidos: [...estado.concluidos, index] });
    tentarTocar();
  }

  function tentarTocar(): void {
    if (estado.tocando !== null || inteiro !== null) return;
    const index = proximo;
    const audio = players.get(index);
    if (!audio) return;
    publicar({ tocando: index });
    desarmarVigia();
    cancelarVigia = opcoes.agendar(() => opcoes.aoTravar(index), prazo);
    audio.play().catch(() => opcoes.aoTravar(index));
  }

  function montar(trecho: TrechoDaFila): AudioDaFila {
    const minha = geracao;
    const audio = opcoes.criarAudio();
    audio.preload = 'auto';
    audio.addEventListener('playing', () => {
      if (minha === geracao && players.get(trecho.index) === audio) {
        aoFicarAudivel(trecho.index);
      }
    });
    audio.addEventListener('ended', () => {
      if (minha === geracao && players.get(trecho.index) === audio) {
        aoTerminar(trecho.index);
      }
    });
    audio.addEventListener('error', () => {
      if (minha === geracao && players.get(trecho.index) === audio) {
        opcoes.aoTravar(trecho.index);
      }
    });
    audio.src = trecho.url;
    audio.load();
    return audio;
  }

  return {
    enfileirar(trecho) {
      if (vistos.has(trecho.index)) return;
      vistos.add(trecho.index);
      players.set(trecho.index, montar(trecho));
      tentarTocar();
    },

    renovar(trecho) {
      const antigo = players.get(trecho.index);
      if (antigo) liberar(antigo);
      players.set(trecho.index, montar(trecho));
      if (estado.tocando === trecho.index) {
        publicar({ tocando: null });
        tentarTocar();
      }
    },

    tocarInteiro(url) {
      desarmarVigia();
      for (const audio of players.values()) liberar(audio);
      players.clear();
      const minha = ++geracao;
      const audio = opcoes.criarAudio();
      inteiro = audio;
      audio.addEventListener('ended', () => {
        if (minha === geracao) publicar({ tocando: null });
      });
      audio.src = url;
      publicar({ tocando: null });
      audio.play().catch(() => undefined);
    },

    limpar() {
      geracao += 1;
      desarmarVigia();
      for (const audio of players.values()) liberar(audio);
      if (inteiro) liberar(inteiro);
      players.clear();
      vistos.clear();
      inteiro = null;
      proximo = 0;
      fimDoAnterior = null;
      estado = ESTADO_VAZIO;
      opcoes.aoMudar(estado);
    },

    estado: () => estado,
  };
}
