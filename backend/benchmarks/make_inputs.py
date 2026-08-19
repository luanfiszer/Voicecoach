"""Constrói os insumos fixos de áudio a partir de uma pasta de origem.

Uso:
    python make_inputs.py <pasta-com-audio>

Grava `inputs/curto.wav` e `inputs/longo.wav` em 16 kHz mono. Gravar em WAV
tira o custo de decodificação de dentro da medição de STT (que é medido à
parte) e deixa os arquivos byte-idênticos entre execuções — é o que torna
"mesmo insumo" verificável em vez de prometido.

O áudio de origem NÃO está no repositório (ver README). Os números só se
comparam entre si quando o insumo é o mesmo: rode este script uma vez, anote
os hashes, e reuse os WAVs.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from _common import INPUT_DIR, SAMPLE_RATE
from faster_whisper.audio import decode_audio

ALVO_CURTO_S = 20.0
ALVO_LONGO_S = 60.0


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
        destino = INPUT_DIR / f"{nome}.wav"
        sf.write(destino, dados, SAMPLE_RATE, subtype="PCM_16")
        digest = hashlib.sha256(destino.read_bytes()).hexdigest()
        print(f"{nome}.wav  {len(dados) / SAMPLE_RATE:6.2f}s  sha256={digest[:16]}…")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(Path(sys.argv[1])))
