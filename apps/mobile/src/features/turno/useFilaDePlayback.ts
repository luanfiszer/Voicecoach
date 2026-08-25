/**
 * A fila de playback: N trechos tocados em sequência, sem buraco audível.
 *
 * **A decisão central, e o motivo dela.** Há um `AudioPlayer` **por trecho**,
 * criado no instante em que o evento `chunk` chega — não um player só chamando
 * `replace(url)` a cada trecho. A diferença é observável e é o critério de
 * aceite: com um player só, o download e a decodificação do trecho N+1 só
 * começam quando o N termina, e caem **dentro** do gap. Criar o player na
 * chegada faz o carregamento acontecer enquanto o trecho anterior ainda toca —
 * o prefetch do card, sem `expo-file-system` e sem dependência nova (ADR-0044).
 *
 * **A ordem é o `index`, nunca a de chegada** (ADR-0023 item 2: *"o instante de
 * criação é medição, a ordem é contrato de playback"*). E a comparação é
 * numérica: `chunk:10` vem depois de `chunk:2`, e comparação de string diz o
 * contrário — é o mesmo bug que o ADR-0041 evitou no servidor.
 *
 * **Dedup por índice** (ADR-0041 item 3): o histórico da retomada e o canal ao
 * vivo podem entregar o mesmo trecho. Sem descartar a repetição, o modo de falha
 * é o aluno **ouvindo a mesma frase duas vezes** — intermitente, porque depende
 * da janela entre a leitura do banco e o início do consumo.
 *
 * Idioma sem paralelo no React web: os players são **objetos nativos** com vida
 * própria e memória fora do JavaScript. Eles não são estado do React — vivem em
 * `useRef` e precisam de `remove()` explícito, ou a memória do áudio vaza.
 */

import type { Trecho } from '@voicecoach/api-client';
import { type AudioPlayer, createAudioPlayer, setAudioModeAsync } from 'expo-audio';
import { useCallback, useEffect, useRef, useState } from 'react';

export type EstadoDaFila = {
  /** O `index` do trecho tocando agora, ou `null` se nada toca. */
  tocando: number | null;
  /** Índices já tocados até o fim. */
  concluidos: number[];
  /**
   * Gaps medidos entre trechos, em ms — do `didJustFinish` do trecho N ao
   * primeiro instante audível do N+1.
   */
  gaps: number[];
  /**
   * O instante (`Date.now()`) em que o PRIMEIRO trecho ficou audível.
   *
   * **O marco é `playing === true` E `currentTime > 0`**, não o retorno de
   * `play()`: `play()` retornar é o pedido aceito, não o som saindo do
   * alto-falante (§4.7 do card). Número sem método declarado é anedota.
   */
  primeiroAudivelEm: number | null;
};

export type Fila = EstadoDaFila & {
  /** Entrega um trecho à fila. Repetição de índice é descartada. */
  enfileirar: (trecho: Trecho) => void;
  /** Troca a URL de um trecho que não carregou e tenta de novo. */
  renovar: (trecho: Trecho) => void;
  /** Abandona a fila e toca o áudio inteiro — o recuo do ADR-0024 item 5. */
  tocarInteiro: (url: string) => void;
  /** Descarta tudo e libera os players nativos. */
  limpar: () => void;
};

export type OpcoesDaFila = {
  /**
   * Chamado quando um trecho **não fica audível** dentro do prazo.
   *
   * O `expo-audio` **não emite evento de erro de carga**: uma URL assinada que
   * expirou devolve 403, o player simplesmente nunca carrega, e o sintoma é
   * silêncio — não exceção. Sem este watchdog, "URL expirada" é um app parado
   * para sempre, que é o oposto da degradação honesta do ADR-0024 item 5.
   */
  aoTravar?: (index: number) => void;
};

/**
 * Quanto se espera um trecho ficar audível antes de chamá-lo de travado.
 *
 * Generoso de propósito: um trecho normal fica audível em ~180 ms (medido), e
 * declarar falha cedo demais transformaria uma rede lenta em erro de produto.
 */
const PRAZO_DE_CARGA_MS = 4000;

const VAZIO: EstadoDaFila = {
  tocando: null,
  concluidos: [],
  gaps: [],
  primeiroAudivelEm: null,
};

export function useFilaDePlayback(opcoes: OpcoesDaFila = {}): Fila {
  const [estado, setEstado] = useState<EstadoDaFila>(VAZIO);

  // O callback vive num ref para que o `enfileirar` não mude de identidade a
  // cada render do chamador — se mudasse, todo `useCallback` abaixo dele
  // nasceria novo e o `useEffect` que consome a fila rodaria em loop.
  const aoTravar = useRef(opcoes.aoTravar);
  aoTravar.current = opcoes.aoTravar;

  // Tudo o que a máquina precisa entre renders vive em refs: os players são
  // nativos, e ler estado do React dentro de um listener nativo daria o valor
  // congelado do render em que o listener nasceu.
  const players = useRef(new Map<number, AudioPlayer>());
  const vistos = useRef(new Set<number>());
  const proximo = useRef(0);
  const tocandoAgora = useRef<number | null>(null);
  const fimDoAnterior = useRef<number | null>(null);
  const jaAudivel = useRef(new Set<number>());
  const vigia = useRef<ReturnType<typeof setTimeout> | null>(null);

  const soltarTudo = useCallback(() => {
    for (const player of players.current.values()) {
      try {
        player.remove();
      } catch {
        // Um player já removido lança; não é falha do produto.
      }
    }
    if (vigia.current) clearTimeout(vigia.current);
    vigia.current = null;
    players.current.clear();
    vistos.current.clear();
    jaAudivel.current.clear();
    proximo.current = 0;
    tocandoAgora.current = null;
    fimDoAnterior.current = null;
  }, []);

  const limpar = useCallback(() => {
    soltarTudo();
    setEstado(VAZIO);
  }, [soltarTudo]);

  // Só desmontando: a fila é liberada por `limpar()` durante a vida da tela.
  useEffect(() => soltarTudo, [soltarTudo]);

  /** Toca o próximo índice esperado, se o player dele já existir. */
  const tocarProximo = useCallback(() => {
    if (tocandoAgora.current !== null) return;

    const indice = proximo.current;
    const player = players.current.get(indice);
    if (!player) return; // ainda não chegou; `enfileirar` tenta de novo

    tocandoAgora.current = indice;
    setEstado((atual) => ({ ...atual, tocando: indice }));
    player.play();

    // O watchdog: se este trecho não ficar audível no prazo, quem chamou
    // decide o que fazer (repedir a URL, tocar o inteiro, ou desistir do áudio).
    if (vigia.current) clearTimeout(vigia.current);
    vigia.current = setTimeout(() => {
      if (jaAudivel.current.has(indice)) return;
      aoTravar.current?.(indice);
    }, PRAZO_DE_CARGA_MS);
  }, []);

  const enfileirar = useCallback(
    (trecho: Trecho) => {
      // Dedup (ADR-0041 item 3). Chega ANTES de criar o player: criar dois
      // players para o mesmo trecho tocaria a frase duas vezes.
      if (vistos.current.has(trecho.index)) return;
      vistos.current.add(trecho.index);

      // Criar o player É o prefetch: a partir daqui o áudio começa a carregar,
      // em paralelo com o que estiver tocando.
      //
      // `updateInterval: 50` não é capricho: o default é **500 ms**, e a
      // primeira leva de 10 execuções mediu gap de 594 ms — praticamente uma
      // tick, quase idêntico em 6 de 7 rodadas. Era o RELÓGIO, não o produto.
      // Um instrumento de 500 ms não julga um critério de 150 ms.
      const player = createAudioPlayer({ uri: trecho.url }, { updateInterval: 50 });
      players.current.set(trecho.index, player);

      player.addListener('playbackStatusUpdate', (status) => {
        if (tocandoAgora.current !== trecho.index) return;

        // O marco de "audível": o som saiu, e não apenas foi pedido.
        if (
          status.playing &&
          status.currentTime > 0 &&
          !jaAudivel.current.has(trecho.index)
        ) {
          jaAudivel.current.add(trecho.index);
          if (vigia.current) {
            clearTimeout(vigia.current);
            vigia.current = null;
          }
          const agora = Date.now();
          const anterior = fimDoAnterior.current;
          setEstado((atual) => ({
            ...atual,
            primeiroAudivelEm: atual.primeiroAudivelEm ?? agora,
            gaps: anterior === null ? atual.gaps : [...atual.gaps, agora - anterior],
          }));
        }

        if (status.didJustFinish) {
          fimDoAnterior.current = Date.now();
          tocandoAgora.current = null;
          proximo.current = trecho.index + 1;
          setEstado((atual) => ({
            ...atual,
            tocando: null,
            concluidos: [...atual.concluidos, trecho.index],
          }));
          tocarProximo();
        }
      });

      tocarProximo();
    },
    [tocarProximo],
  );

  /**
   * Substitui o player de um trecho por outro, com URL nova, e tenta de novo.
   *
   * Uma tentativa só é responsabilidade de quem chama — aqui não há contador,
   * porque repetir a renovação em laço é o que transforma um 403 numa
   * tempestade de requisições.
   */
  const renovar = useCallback(
    (trecho: Trecho) => {
      const antigo = players.current.get(trecho.index);
      if (antigo) {
        try {
          antigo.remove();
        } catch {
          // idem `soltarTudo`
        }
      }
      players.current.delete(trecho.index);
      vistos.current.delete(trecho.index);
      tocandoAgora.current = null;
      proximo.current = trecho.index;
      enfileirar(trecho);
    },
    [enfileirar],
  );

  /**
   * Toca o áudio inteiro em vez dos trechos (ADR-0024 item 5).
   *
   * O caso é o do trecho expirado com `full` presente: o aluno perde a
   * granularidade da cascata, **não** perde a resposta.
   */
  const tocarInteiro = useCallback(
    (url: string) => {
      soltarTudo();
      const player = createAudioPlayer({ uri: url }, { updateInterval: 50 });
      players.current.set(0, player);
      vistos.current.add(0);
      proximo.current = 0;
      player.addListener('playbackStatusUpdate', (status) => {
        if (status.playing && status.currentTime > 0 && !jaAudivel.current.has(0)) {
          jaAudivel.current.add(0);
          const agora = Date.now();
          setEstado((atual) => ({
            ...atual,
            primeiroAudivelEm: atual.primeiroAudivelEm ?? agora,
          }));
        }
        if (status.didJustFinish) {
          tocandoAgora.current = null;
          setEstado((atual) => ({ ...atual, tocando: null, concluidos: [0] }));
        }
      });
      tocandoAgora.current = 0;
      setEstado((atual) => ({ ...atual, tocando: 0 }));
      player.play();
    },
    [soltarTudo],
  );

  return { ...estado, enfileirar, renovar, tocarInteiro, limpar };
}

/**
 * Prepara a sessão de áudio para TOCAR.
 *
 * Herança do CARD-011: no iOS, `allowsRecording: true` joga o playback para o
 * alto-falante do ouvido, baixinho. Desligá-lo antes de tocar é o que faz a voz
 * do professor sair no alto-falante de verdade.
 */
export async function prepararParaTocar(): Promise<void> {
  await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true });
}
