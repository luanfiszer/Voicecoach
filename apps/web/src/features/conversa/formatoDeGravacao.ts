/**
 * Em que formato o navegador grava (CARD-065) — a diferença de plataforma
 * mais concreta da fase 2.
 *
 * Chrome e Firefox gravam `audio/webm;codecs=opus`; o Safari só grava
 * `audio/mp4` (AAC). O backend aceita os dois (`api/audio_intake.py`) e mede a
 * duração pelas AMOSTRAS decodificadas, não pelo cabeçalho — o que importa
 * porque o WebM do `MediaRecorder` sai sem duração no cabeçalho (demonstrado
 * no CARD-065: `stream.duration = None`, e o servidor respondeu 202 com 3,96 s
 * medidos).
 */

export type FormatoDeGravacao = {
  /** O que se pede ao `MediaRecorder`. */
  mimeType: string;
  /** A extensão do nome do arquivo no multipart. */
  extensao: 'webm' | 'm4a' | 'ogg';
};

/** Em ordem de preferência: Opus é menor que AAC para fala. */
const CANDIDATOS: FormatoDeGravacao[] = [
  { mimeType: 'audio/webm;codecs=opus', extensao: 'webm' },
  { mimeType: 'audio/webm', extensao: 'webm' },
  { mimeType: 'audio/mp4', extensao: 'm4a' },
  { mimeType: 'audio/ogg;codecs=opus', extensao: 'ogg' },
];

/**
 * O primeiro formato que o navegador grava, ou `null` se nenhum.
 *
 * `suporta` é `MediaRecorder.isTypeSupported` — injetado para o teste rodar
 * em Node, onde `MediaRecorder` não existe.
 */
export function escolherFormato(
  suporta: (mimeType: string) => boolean,
): FormatoDeGravacao | null {
  return CANDIDATOS.find((c) => suporta(c.mimeType)) ?? null;
}

/**
 * O `Content-Type` do upload: o tipo REAL que o gravador produziu
 * (`MediaRecorder.mimeType`), que pode trazer `;codecs=…` — o servidor corta
 * no `;` antes de comparar.
 */
export function tipoDoUpload(mimeTypeReal: string, pedido: FormatoDeGravacao): string {
  return mimeTypeReal.length > 0 ? mimeTypeReal : pedido.mimeType;
}
