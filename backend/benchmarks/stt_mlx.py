"""STT com `mlx-whisper` (GPU do Apple Silicon).

Mesmo insumo e mesmo protocolo do `stt_faster_whisper.py`, para que as duas
tabelas se comparem linha a linha.

APENAS APPLE SILICON. Numa máquina x86 este script não roda — o que é
exatamente o motivo de o adapter de STT precisar de duas implementações.
"""

from __future__ import annotations

from typing import Any

import mlx_whisper
import soundfile as sf
from _common import INPUT_DIR, SAMPLE_RATE, cronometra, grava, resume

REPOSITORIOS = (
    "mlx-community/whisper-small.en-mlx",
    "mlx-community/whisper-base.en-mlx",
)


def mede(repo: str, audio_nome: str, n: int) -> dict[str, Any]:
    audio, _ = sf.read(INPUT_DIR / f"{audio_nome}.wav", dtype="float32")
    duracao = len(audio) / SAMPLE_RATE

    def uma_vez() -> str:
        saida = mlx_whisper.transcribe(
            audio, path_or_hf_repo=repo, language="en", verbose=None
        )
        return str(saida["text"]).strip()

    tempos, texto = cronometra(uma_vez, n)
    return {
        "repo": repo,
        "audio": audio_nome,
        **resume(tempos, duracao),
        "texto": texto,
    }


def main() -> None:
    resultados = []
    for repo in REPOSITORIOS:
        for audio_nome, n in (("curto", 5), ("longo", 3)):
            r = mede(repo, audio_nome, n)
            resultados.append(r)
            print(
                f"{repo.split('/')[-1]:26s} {audio_nome:5s} "
                f"p50={r['p50_s']:6.2f}s rtf={r['rtf']}",
                flush=True,
            )
    print(f"\nresultados em {grava('stt_mlx', resultados)}")


if __name__ == "__main__":
    main()
