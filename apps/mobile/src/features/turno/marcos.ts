/**
 * Os quatro marcos da medição ponta a ponta — o número do produto.
 *
 * Todos os números do projeto até aqui são de componentes ou do pipeline do
 * servidor (`docs/medicao-latencia.md` §10: 1,56–1,61 s até o primeiro trecho
 * gravado, com storage e repositório em memória). O que nunca foi medido é o que
 * sobra por fora: upload, pickup da fila, transporte, download do trecho,
 * decodificação e início do playback.
 *
 * **O método é declarado, não subentendido.** Cada marco diz de que instante ele
 * fala, porque um número sem método é anedota:
 *
 * | Marco | O instante exato |
 * |---|---|
 * | `parouDeFalar` | `recorder.stop()` retornou — o dedo saiu do botão |
 * | `uploadCompleto` | o `202` do `POST` chegou, com `turn_id` |
 * | `primeiroChunk` | o evento `chunk` de índice 0 foi lido do stream |
 * | `primeiroAudivel` | o player reportou `playing && currentTime > 0` |
 *
 * O quarto é o traiçoeiro e está escrito de propósito: `player.play()`
 * **retornar** não é o som saindo do alto-falante.
 */

export type Marcos = {
  parouDeFalar: number | null;
  uploadCompleto: number | null;
  primeiroChunk: number | null;
  primeiroAudivel: number | null;
};

export const MARCOS_VAZIOS: Marcos = {
  parouDeFalar: null,
  uploadCompleto: null,
  primeiroChunk: null,
  primeiroAudivel: null,
};

/** Os intervalos entre marcos, em ms. `null` onde o marco não existe. */
export type Intervalos = {
  upload: number | null;
  ateOChunk: number | null;
  ateOAudio: number | null;
  /** O número do produto: do dedo sair do botão à primeira palavra. */
  total: number | null;
};

function delta(de: number | null, ate: number | null): number | null {
  return de === null || ate === null ? null : ate - de;
}

export function intervalos(m: Marcos): Intervalos {
  return {
    upload: delta(m.parouDeFalar, m.uploadCompleto),
    ateOChunk: delta(m.uploadCompleto, m.primeiroChunk),
    ateOAudio: delta(m.primeiroChunk, m.primeiroAudivel),
    total: delta(m.parouDeFalar, m.primeiroAudivel),
  };
}

/** Mediana. `p50` exige repetição — uma execução não tem mediana. */
export function p50(valores: number[]): number | null {
  if (valores.length === 0) return null;
  const ordenados = [...valores].sort((a, b) => a - b);
  const meio = Math.floor(ordenados.length / 2);
  if (ordenados.length % 2 === 1) return ordenados[meio] ?? null;
  const esquerda = ordenados[meio - 1];
  const direita = ordenados[meio];
  if (esquerda === undefined || direita === undefined) return null;
  return (esquerda + direita) / 2;
}

export function formatar(ms: number | null): string {
  return ms === null ? '—' : `${(ms / 1000).toFixed(2)}s`;
}
