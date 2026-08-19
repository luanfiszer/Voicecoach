"""Constrói os insumos fixos de áudio a partir de uma pasta de origem.

Uso:
    python make_inputs.py <pasta-com-audio>

Grava, para cada duração alvo, o mesmo áudio em três formatos a 16 kHz mono:

- `.wav` (PCM 16), o insumo dos benchmarks de STT. Gravar em WAV tira o custo
  de decodificação de dentro da medição de STT (que é medido à parte, em
  `stt_decode.py`) e deixa os arquivos byte-idênticos entre execuções — é o que
  torna "mesmo insumo" verificável em vez de prometido;
- `.m4a` (AAC 64 kbps), que é o que o Expo grava por padrão no iOS e no
  Android — ou seja, o formato que o adapter de STT vai **de fato** receber;
- `.opus` (Ogg/Opus 24 kbps), o formato do protótipo de WhatsApp, mantido
  porque decodificá-lo custa cerca de 5 vezes o AAC e é a única variante que
  chega a aparecer no orçamento de latência.

Os três saem do MESMO PCM: comparar decodificação entre formatos só significa
alguma coisa quando o áudio por trás é idêntico.

O áudio de origem NÃO está no repositório (ver README). Os números só se
comparam entre si quando o insumo é o mesmo: rode este script uma vez, anote
os hashes, e reuse os arquivos.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import av
import numpy as np
import soundfile as sf
from _common import INPUT_DIR, SAMPLE_RATE
from faster_whisper.audio import decode_audio

ALVO_CURTO_S = 20.0
ALVO_LONGO_S = 60.0

# (extensão, codec, container, bitrate). O bitrate é o de cada codec no uso
# real: 64 kbps é o default de gravação de voz do Expo; 24 kbps é a faixa em
# que o Opus é usado para fala.
FORMATOS_COMPRIMIDOS = (
    ("m4a", "aac", "mp4", 64_000),
    ("opus", "libopus", "ogg", 24_000),
)


def comprime(
    origem: Path, destino: Path, codec: str, container: str, bitrate: int
) -> None:
    """Reencoda um WAV para um formato comprimido, sem passar pelo `ffmpeg` CLI.

    A codificação é feita com PyAV (binding do libav*, que vem junto do
    `faster-whisper`) e não com o binário `ffmpeg`: a máquina de desenvolvimento
    não o tem no PATH, e depender dele aqui recriaria exatamente a armadilha que
    o adapter de STT evita — o `mlx_whisper.load_audio()` exige `ffmpeg` no PATH
    quando recebe um caminho de arquivo.
    """
    with (
        av.open(str(origem)) as entrada,
        av.open(str(destino), mode="w", format=container) as saida,
    ):
        stream = saida.add_stream(codec, rate=SAMPLE_RATE)
        stream.bit_rate = bitrate
        for quadro in entrada.decode(audio=0):
            # `pts = None` deixa o encoder recalcular o carimbo de tempo. Sem
            # isso, os carimbos do arquivo de origem vazam para um stream com
            # outra base de tempo e o arquivo sai com duração errada.
            quadro.pts = None
            for pacote in stream.encode(quadro):
                saida.mux(pacote)
        for pacote in stream.encode():  # drena o que ficou no buffer do encoder
            saida.mux(pacote)


def relata(destino: Path, duracao_s: float) -> None:
    digest = hashlib.sha256(destino.read_bytes()).hexdigest()
    tamanho_kb = destino.stat().st_size / 1024
    print(
        f"{destino.name:12s} {duracao_s:6.2f}s {tamanho_kb:8.0f} KB "
        f"sha256={digest[:16]}…"
    )


def main(origem: Path) -> int:
    arquivos = sorted(
        p for p in origem.iterdir() if p.suffix in {".mp3", ".m4a", ".wav"}
    )
    if not arquivos:
        print(f"Nenhum áudio em {origem}", file=sys.stderr)
        return 1

    faixas = [decode_audio(str(p), sampling_rate=SAMPLE_RATE) for p in arquivos]

    # Curto: a faixa mais longa que ainda cabe no alvo — sem cortar no meio de
    # uma frase, que estragaria a avaliação de qualidade.
    curto = max(
        (f for f in faixas if len(f) / SAMPLE_RATE <= ALVO_CURTO_S),
        key=len,
        default=faixas[0],
    )
    # Longo: concatena até cruzar o alvo.
    acumulado: list[np.ndarray] = []
    total = 0.0
    for faixa in sorted(faixas, key=len, reverse=True):
        acumulado.append(faixa)
        total += len(faixa) / SAMPLE_RATE
        if total >= ALVO_LONGO_S:
            break
    longo = np.concatenate(acumulado)

    INPUT_DIR.mkdir(exist_ok=True)
    for nome, dados in (("curto", curto), ("longo", longo)):
        duracao_s = len(dados) / SAMPLE_RATE

        wav = INPUT_DIR / f"{nome}.wav"
        sf.write(wav, dados, SAMPLE_RATE, subtype="PCM_16")
        relata(wav, duracao_s)

        # Os comprimidos saem do WAV recém-gravado, não da origem: assim os três
        # formatos carregam exatamente o mesmo PCM.
        for extensao, codec, container, bitrate in FORMATOS_COMPRIMIDOS:
            destino = INPUT_DIR / f"{nome}.{extensao}"
            comprime(wav, destino, codec, container, bitrate)
            relata(destino, duracao_s)
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(Path(sys.argv[1])))
