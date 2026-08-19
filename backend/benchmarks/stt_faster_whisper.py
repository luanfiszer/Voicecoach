"""STT com `faster-whisper` (CPU, CTranslate2): varredura de modelo e parâmetros.

Protocolo em `_common.py`. O modelo é carregado UMA vez por configuração e
reaproveitado entre as repetições — é o cenário "residente no worker".

A carga do modelo é medida à parte, porque responde outra pergunta: se o
worker mantém o modelo na memória ou o carrega por job.
"""

from __future__ import annotations

import statistics
from time import perf_counter
from typing import Any

import soundfile as sf
from _common import INPUT_DIR, SAMPLE_RATE, cronometra, grava, resume
from faster_whisper import WhisperModel

REPETICOES_CURTO = 5
REPETICOES_LONGO = 3


def tempo_de_carga(modelo: str, quantizacao: str, amostras: int = 3) -> float:
    """Mediana do tempo de carga com o modelo já em disco."""
    tempos: list[float] = []
    for _ in range(amostras + 1):
        inicio = perf_counter()
        WhisperModel(modelo, device="cpu", compute_type=quantizacao)
        tempos.append(perf_counter() - inicio)
    return round(statistics.median(tempos[1:]), 3)


def transcreve(
    modelo: str,
    quantizacao: str,
    beam: int,
    *,
    vad: bool,
    audio_nome: str,
    n: int,
) -> dict[str, Any]:
    motor = WhisperModel(modelo, device="cpu", compute_type=quantizacao)
    audio, _ = sf.read(INPUT_DIR / f"{audio_nome}.wav", dtype="float32")
    duracao = len(audio) / SAMPLE_RATE

    def uma_vez() -> str:
        segmentos, _ = motor.transcribe(
            audio, language="en", beam_size=beam, vad_filter=vad
        )
        # O generator só executa aqui: sem consumir, a medição cronometraria a
        # criação do iterador, não a transcrição.
        return " ".join(s.text.strip() for s in segmentos)

    tempos, texto = cronometra(uma_vez, n)
    return {
        "modelo": modelo,
        "quantizacao": quantizacao,
        "beam_size": beam,
        "vad": vad,
        "audio": audio_nome,
        **resume(tempos, duracao),
        "texto": texto,
    }


def main() -> None:
    resultados: dict[str, Any] = {"carga": {}, "transcricao": []}

    for modelo, quantizacao in (
        ("small", "int8"),
        ("small.en", "int8"),
        ("base.en", "int8"),
        ("small.en", "float32"),
    ):
        chave = f"{modelo}/{quantizacao}"
        resultados["carga"][chave] = tempo_de_carga(modelo, quantizacao)
        print(f"carga {chave}: {resultados['carga'][chave]}s", flush=True)

    for modelo in ("small", "small.en", "base.en"):
        for beam in (5, 1):
            for vad in (True, False):
                r = transcreve(
                    modelo,
                    "int8",
                    beam,
                    vad=vad,
                    audio_nome="curto",
                    n=REPETICOES_CURTO,
                )
                resultados["transcricao"].append(r)
                print(
                    f"{modelo:9s} int8    beam{beam} vad={vad!s:5s} curto  "
                    f"p50={r['p50_s']:6.2f}s rtf={r['rtf']}",
                    flush=True,
                )

    # Quantização: int8 vs float32 numa configuração só. O resultado
    # contraintuitivo (float32 mais rápido no Apple Silicon) está em docs/.
    r = transcreve(
        "small.en", "float32", 1, vad=True, audio_nome="curto", n=REPETICOES_CURTO
    )
    resultados["transcricao"].append(r)
    print(
        f"small.en  float32 beam1 vad=True  curto  p50={r['p50_s']:6.2f}s", flush=True
    )

    for modelo, beam in (("small.en", 5), ("small.en", 1), ("base.en", 1)):
        r = transcreve(
            modelo, "int8", beam, vad=True, audio_nome="longo", n=REPETICOES_LONGO
        )
        resultados["transcricao"].append(r)
        print(
            f"{modelo:9s} int8    beam{beam} vad=True  longo  "
            f"p50={r['p50_s']:6.2f}s rtf={r['rtf']}",
            flush=True,
        )

    print(f"\nresultados em {grava('stt_faster_whisper', resultados)}")


if __name__ == "__main__":
    main()
