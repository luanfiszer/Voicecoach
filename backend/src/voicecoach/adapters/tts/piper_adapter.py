"""Adapter do Piper — o motor de voz default (ADR da troca, CARD-008).

Escolhido por medição, não por gosto (§9 da medição): contra o Kokoro, 10x mais
rápido para carregar (0,55 s vs. 5,66 s), RTF 4x menor (0,024 vs. 0,098) e
**zero dependências de sistema** — ele embarca o `espeak-ng-data` no próprio
wheel e fonemiza numa extensão compilada.

Dois detalhes de forma que valem mais que a velocidade:

1. **O Piper devolve PCM16 pronto** (`chunk.audio_int16_bytes`). É exatamente o
   que a porta trafega, então não há conversão de formato nesta fronteira — nem
   `ndarray` transitando, nem recodificação.
2. **Ele não baixa nada em runtime.** A voz é um par `.onnx` + `.onnx.json` que
   alguém buscou antes; se faltar, o adapter falha **na subida**, dizendo qual
   arquivo procurar. O Kokoro, no mesmo teste, disparou dois downloads no meio
   da execução — num container sem rede isso não é lentidão, é falha.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from typing import TYPE_CHECKING

from voicecoach.application.ports.text_to_speech import (
    SynthesizedAudio,
    TtsError,
)

if TYPE_CHECKING:
    from pathlib import Path

    from piper import PiperVoice

logger = logging.getLogger(__name__)


class TtsVoiceNotFoundError(RuntimeError):
    """O arquivo da voz não está onde a configuração aponta.

    `RuntimeError` e não `DomainError` (ADR-0017), e levantado **na subida** —
    como o `SttProviderUnavailableError`, é configuração impossível de
    satisfazer, e ninguém a captura. Falhar aqui é o que impede um worker de
    aceitar jobs que ele não consegue completar (ADR-0025).
    """


class PiperTts:
    """Sintetiza uma sentença por chamada, num executor.

    O motor é **CPU-bound** — este é o caso em que o argumento do adapter de STT
    de fato transfere (ver `faster_whisper_adapter.py`): o `onnxruntime` roda em
    código nativo e solta o GIL, então a thread do executor de fato trabalha em
    paralelo com o event loop, em vez de só desbloqueá-lo.
    """

    def __init__(self, voice: PiperVoice) -> None:
        self._voice = voice
        self._sample_rate = int(voice.config.sample_rate)

    async def synthesize(self, text: str) -> SynthesizedAudio:
        loop = asyncio.get_running_loop()
        pcm = await loop.run_in_executor(
            None, functools.partial(self._synthesize_blocking, text)
        )
        return SynthesizedAudio(pcm=pcm, sample_rate=self._sample_rate)

    def _synthesize_blocking(self, text: str) -> bytes:
        try:
            chunks = list(self._voice.synthesize(text))
        except Exception as exc:
            message = f"Piper falhou ao sintetizar: {exc}"
            raise TtsError(message) from exc

        if not chunks:
            message = f"Piper devolveu zero amostras para {text!r}"
            raise TtsError(message)

        # `b"".join` porque o Piper já entrega PCM16: nada a converter.
        return b"".join(c.audio_int16_bytes for c in chunks)


def load_piper(voices_dir: Path, voice_name: str) -> PiperTts:
    """Carrega a voz do disco — a carga cara, paga uma vez na subida (ADR-0025).

    Medido em **0,43 s**, contra 3,21 s do `KPipeline` do Kokoro. É por isso que
    os "~6 s de carga do worker" do ADR-0025 deixam de ser verdade com este
    adapter: o dono daqueles segundos era o TTS.
    """
    from piper import PiperVoice

    model = voices_dir / f"{voice_name}.onnx"
    if not model.exists():
        message = (
            f"voz do Piper não encontrada: {model}. Baixe com\n"
            f"  python -m piper.download_voices {voice_name} "
            f"--download-dir {voices_dir}"
        )
        raise TtsVoiceNotFoundError(message)

    logger.info("TTS: carregando voz piper '%s' de %s", voice_name, voices_dir)
    return PiperTts(PiperVoice.load(model))
