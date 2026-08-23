"""TTS local com Piper: carga do modelo e síntese — o par do `tts_kokoro.py`.

Mesmos dois textos, mesmo protocolo (`_common.py`), mesma máquina. A comparação
só vale porque nada além do motor muda:
  - TIPICO: resposta de 3-5 frases, o tamanho que o prompt do professor pede
  - FRASE : só a primeira frase — o que a cascata libera primeiro

DIFERENÇA DE EMPACOTAMENTO em relação ao Kokoro, que é o que este script existe
para medir junto do tempo:

1. **Nenhuma dependência de sistema.** O Piper embarca `espeak-ng-data` DENTRO
   do pacote (`site-packages/piper/espeak-ng-data`) e fonemiza numa extensão
   compilada (`espeakbridge.so`). Não há `brew install`, não há `.dylib` com
   caminho de CI compilado dentro, não há reapontar wrapper depois do import —
   as três armadilhas da medição §4.3.
2. **Em troca, a voz é um download à parte.** Cada voz é um par
   `.onnx` (60 MB) + `.onnx.json`, o análogo exato dos pesos do Whisper. É
   troca, não eliminação: some a dependência de sistema, entra um artefato
   versionado. Baixe antes de rodar (ver README).
3. **O Piper publica `py.typed`**; o Kokoro não. Importa para o `mypy --strict`
   do produto, não para este script.

O `audio_int16_bytes` de cada chunk já é **PCM16 little-endian mono** — o mesmo
formato que a porta `TextToSpeech` trafega. Nada de `ndarray` no caminho.
"""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
import soundfile as sf
from _common import cronometra, grava, resume
from piper import PiperVoice

VOICE_DIR = Path(__file__).resolve().parent / "voices"

# Duas vozes femininas en_US, para a coluna de qualidade percebida ter amostra —
# o Kokoro foi medido com `af_heart`, também feminina americana. A `lessac` é a
# voz de referência do Piper; a `amy` é a alternativa mais citada.
VOZES = ("en_US-lessac-medium", "en_US-amy-medium")

TIPICO = (
    "That's a great point! I understand what you mean about your job being "
    "stressful sometimes. Working in a hospital must be really demanding, "
    "especially during long shifts. Have you found any particular way to "
    "relax after work? Maybe listening to music or going for a walk helps."
)
FRASE = "That's a great point, and I understand exactly what you mean."


def sintetiza(voice: PiperVoice, texto: str) -> tuple[bytes, int]:
    """Concatena os chunks em PCM16 cru — `b"".join`, sem recodificar nada.

    É a operação que a porta `TextToSpeech` torna barata (ADR do CARD-008):
    juntar PCM é somar listas de amostras. Com áudio já comprimido, isto seria
    decodificar tudo de volta e comprimir outra vez.
    """
    chunks = list(voice.synthesize(texto))
    return b"".join(c.audio_int16_bytes for c in chunks), chunks[0].sample_rate


def main() -> None:
    resultados: dict[str, Any] = {"vozes": []}

    for nome_voz in VOZES:
        inicio = perf_counter()
        voice = PiperVoice.load(VOICE_DIR / f"{nome_voz}.onnx")
        carga_s = round(perf_counter() - inicio, 2)
        taxa = voice.config.sample_rate
        print(f"\n{nome_voz}: carga {carga_s}s, {taxa} Hz", flush=True)

        medidas: dict[str, Any] = {
            "voz": nome_voz,
            "carga_s": carga_s,
            "sample_rate": taxa,
            "sintese": [],
        }

        for nome, texto in (("tipico", TIPICO), ("frase", FRASE)):

            def uma_vez(t: str = texto, v: PiperVoice = voice) -> bytes:
                return sintetiza(v, t)[0]

            tempos, pcm = cronometra(uma_vez, 5)
            # 2 bytes por amostra (PCM16), mono.
            duracao = len(pcm) / 2 / taxa
            r = {
                "texto": nome,
                "chars": len(texto),
                "audio_s": round(duracao, 2),
                "pcm_bytes": len(pcm),
                **resume(tempos, duracao),
            }
            medidas["sintese"].append(r)
            print(
                f"{nome:7s} {len(texto):3d} chars -> {duracao:5.2f}s de áudio | "
                f"p50={r['p50_s']:6.2f}s rtf={r['rtf']}",
                flush=True,
            )
            amostras = np.frombuffer(pcm, dtype=np.int16)
            sf.write(f"/tmp/tts_piper_{nome_voz}_{nome}.wav", amostras, taxa)

        resultados["vozes"].append(medidas)

    print(f"\nresultados em {grava('tts_piper', resultados)}")


if __name__ == "__main__":
    main()
