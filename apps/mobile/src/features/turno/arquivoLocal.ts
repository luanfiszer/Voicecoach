/**
 * Lê um arquivo do aparelho e o entrega como `Blob`.
 *
 * **Por que isto existe, e não é acidente.** O jeito idiomático do React Native
 * de subir um arquivo é `formData.append('audio', { uri, name, type })` — um
 * objeto que só a camada nativa do RN entende. No Expo SDK 57 o `FormData`
 * global é o do **padrão web**, e ele recusa esse objeto com uma mensagem que
 * não ajuda ninguém:
 *
 * ```
 * ERROR  [turno] falhou no envio: [Error: Unsupported FormDataPart implementation]
 * ```
 *
 * Medido nesta sessão, no Simulador. A saída é mandar um `Blob` de verdade, que
 * é o que as duas metades entendem — e é também o que a web vai mandar quando o
 * companion existir, então o client de `packages/api-client` fica com **um**
 * caminho em vez de dois.
 *
 * **Por que `XMLHttpRequest` e não `fetch`.** O XHR é a implementação do próprio
 * React Native e lê `file://` desde sempre; o `fetch` do Expo é WinterCG e não
 * promete esquema de arquivo. Usar o que tem a garantia custa dez linhas e
 * evita uma classe de bug que só aparece em aparelho.
 *
 * Sem paralelo no React web: lá um arquivo já chega como `File` do `<input>`.
 * Aqui ele é um caminho no sistema de arquivos do aparelho, e alguém precisa
 * materializar os bytes antes de eles existirem para o JavaScript.
 */

export async function lerComoBlob(uri: string, tipo: string): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const requisicao = new XMLHttpRequest();
    requisicao.responseType = 'blob';
    requisicao.onload = () => {
      const corpo: unknown = requisicao.response;
      if (corpo instanceof Blob) {
        // O `type` do blob vira o `Content-Type` da parte do multipart, e é ele
        // que o servidor valida contra a lista fechada de `audio_intake.py`.
        resolve(corpo.slice(0, corpo.size, tipo));
        return;
      }
      reject(new Error(`não consegui ler ${uri} como Blob`));
    };
    requisicao.onerror = () => reject(new Error(`falha ao ler ${uri}`));
    requisicao.open('GET', uri);
    requisicao.send();
  });
}
