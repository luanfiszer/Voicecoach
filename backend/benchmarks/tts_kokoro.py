"""TTS local com Kokoro: carga do pipeline e síntese.

Dois textos, porque a DIFERENÇA entre eles é o ganho da síntese em cascata:
  - TIPICO: resposta de 3-5 frases, o tamanho que o prompt do professor pede
  - FRASE : só a primeira frase — o que a cascata libera primeiro

ATENÇÃO — dependências de sistema (ver README): o Kokoro exige `espeak-ng`
instalado no sistema e o modelo `en_core_web_sm` do spaCy. O binário que vem
no wheel do `espeakng-loader` tem o caminho de dados da máquina de CI
compilado dentro e falha com "phontab: No such file or directory".
"""

from __future__ import annotations

import os
from time import perf_counter
from typing import Any

import numpy as np
import soundfile as sf
from _common import cronometra, grava, resume
from kokoro import KPipeline
from phonemizer.backend.espeak.wrapper import EspeakWrapper

# Reaponta DEPOIS do import do kokoro: a `misaki` atribui a biblioteca no
# import dela, sobrescrevendo qualquer configuração feita antes.
EspeakWrapper.set_library(
    os.environ.get("ESPEAK_LIB", "/opt/homebrew/lib/libespeak-ng.dylib")
)
EspeakWrapper.set_data_path(
    os.environ.get("ESPEAK_DATA", "/opt/homebrew/share/espeak-ng-data")
)

TAXA_KOKORO = 24_000
VOZ = "af_heart"

TIPICO = (
    "That's a great point! I understand what you mean about your job being "
    "stressful sometimes. Working in a hospital must be really demanding, "
    "especially during long shifts. Have you found any particular way to "
    "relax after work? Maybe listening to music or going for a walk helps."
)
FRASE = "That's a great point, and I understand exactly what you mean."


def main() -> None:
    inicio = perf_counter()
    pipeline = KPipeline(lang_code="a")
    carga_s = round(perf_counter() - inicio, 2)
    print(f"construção do pipeline: {carga_s}s", flush=True)

    resultados: dict[str, Any] = {"carga_pipeline_s": carga_s, "sintese": []}

    for nome, texto in (("tipico", TIPICO), ("frase", FRASE)):

        def uma_vez(t: str = texto) -> np.ndarray:
            return np.concatenate([g.audio.numpy() for g in pipeline(t, voice=VOZ)])

        tempos, audio = cronometra(uma_vez, 5)
        duracao = len(audio) / TAXA_KOKORO
        r = {
            "texto": nome,
            "chars": len(texto),
            "audio_s": round(duracao, 2),
            **resume(tempos, duracao),
        }
        resultados["sintese"].append(r)
        print(
            f"{nome:7s} {len(texto):3d} chars -> {duracao:5.2f}s de áudio | "
            f"p50={r['p50_s']:6.2f}s rtf={r['rtf']}",
            flush=True,
        )
        sf.write(f"/tmp/tts_{nome}.wav", audio, TAXA_KOKORO)

    print(f"\nresultados em {grava('tts_kokoro', resultados)}")


if __name__ == "__main__":
    main()
