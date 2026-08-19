"""Os dois adapters, sem carregar modelo nenhum.

O motor real é substituído por um stub. Isso é possível porque os adapters
recebem o motor pronto em vez de construí-lo — a construção cara mora em
`load_faster_whisper` / `load_mlx_whisper`, exercitadas só no teste `slow`.

O que estes testes protegem: a **fronteira**. Que o adapter decodifica bytes,
consome o generator no lugar certo e devolve `Transcript` — sem que nenhum
detalhe da biblioteca vaze para o valor de retorno.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from voicecoach.adapters.stt.faster_whisper_adapter import (
    FasterWhisperSpeechToText,
)
from voicecoach.adapters.stt.mlx_whisper_adapter import MlxWhisperSpeechToText
from voicecoach.application.ports.speech_to_text import AudioInput, SpeechToText

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray

# 2,3 s de voz sintética (saída de `tts-1`), 16 kHz mono. Versionado de
# propósito: sem ele o critério de aceite só seria verificável na máquina de
# quem gravou o áudio original.
FIXTURE = Path(__file__).parent.parent / "fixtures" / "stt" / "amazing-project.wav"


@dataclass
class _SegmentoFalso:
    text: str


@dataclass
class _InfoFalsa:
    language: str


class _MotorFalso:
    """Imita o `WhisperModel` no pouco que o adapter usa dele.

    `consumido` registra se alguém chegou a percorrer o generator — é o que
    torna observável a armadilha comentada no adapter.
    """

    def __init__(self, textos: list[str]) -> None:
        self._textos = textos
        self.consumido = False
        self.kwargs_recebidos: dict[str, object] = {}
        self.amostras_recebidas: int | None = None

    def transcribe(
        self,
        audio: NDArray[np.float32],
        /,
        *,
        language: str,
        beam_size: int,
        vad_filter: bool,
    ) -> tuple[Iterable[_SegmentoFalso], _InfoFalsa]:
        self.amostras_recebidas = len(audio)
        self.kwargs_recebidos = {
            "language": language,
            "beam_size": beam_size,
            "vad_filter": vad_filter,
        }

        def gerador() -> Iterator[_SegmentoFalso]:
            self.consumido = True
            for texto in self._textos:
                yield _SegmentoFalso(texto)

        return gerador(), _InfoFalsa(language="en")


@pytest.fixture
def audio() -> AudioInput:
    return AudioInput(data=FIXTURE.read_bytes())


async def test_faster_whisper_junta_os_segmentos_num_texto(
    audio: AudioInput,
) -> None:
    motor = _MotorFalso([" Wow, that sounds", " like an amazing project. "])
    adapter: SpeechToText = FasterWhisperSpeechToText(motor)

    resultado = await adapter.transcribe(audio)

    assert resultado.text == "Wow, that sounds like an amazing project."
    assert resultado.language == "en"


async def test_faster_whisper_consome_o_generator(audio: AudioInput) -> None:
    # Se o adapter devolvesse o generator sem percorrê-lo, `text` sairia vazio e
    # o trabalho de CPU aconteceria depois, FORA do executor — no event loop do
    # worker. Esta asserção é o que impede essa regressão de passar batida.
    motor = _MotorFalso(["hello"])
    adapter = FasterWhisperSpeechToText(motor)

    await adapter.transcribe(audio)

    assert motor.consumido is True


async def test_faster_whisper_usa_os_parametros_medidos(
    audio: AudioInput,
) -> None:
    # Não é preciosismo: `beam_size=5` custa ~30% a mais e `int8` é MAIS lento
    # neste hardware (ADR-0027, itens 5 e 6). Um "ajuste" silencioso aqui
    # devolveria a latência que a medição comprou.
    motor = _MotorFalso(["ok"])

    await FasterWhisperSpeechToText(motor).transcribe(audio)

    assert motor.kwargs_recebidos == {
        "language": "en",
        "beam_size": 1,
        "vad_filter": True,
    }


async def test_faster_whisper_decodifica_os_bytes_antes_de_transcrever(
    audio: AudioInput,
) -> None:
    # O motor recebe AMOSTRAS, não bytes: 2,3 s a 16 kHz.
    motor = _MotorFalso(["ok"])

    resultado = await FasterWhisperSpeechToText(motor).transcribe(audio)

    assert motor.amostras_recebidas == pytest.approx(2.3 * 16_000, rel=0.01)
    assert resultado.duration_seconds == pytest.approx(2.3, rel=0.01)


async def test_mlx_extrai_texto_e_duracao(audio: AudioInput) -> None:
    recebido: dict[str, object] = {}

    def transcribe_falso(
        audio_amostras: NDArray[np.float32],
        *,
        path_or_hf_repo: str,
        language: str,
        verbose: bool | None,
    ) -> dict[str, object]:
        recebido["repo"] = path_or_hf_repo
        recebido["language"] = language
        recebido["verbose"] = verbose
        recebido["amostras"] = len(audio_amostras)
        return {"text": "  Wow, that sounds like an amazing project.  "}

    adapter: SpeechToText = MlxWhisperSpeechToText(
        transcribe_falso, "mlx-community/whisper-small.en-mlx"
    )

    resultado = await adapter.transcribe(audio)

    assert resultado.text == "Wow, that sounds like an amazing project."
    assert resultado.duration_seconds == pytest.approx(2.3, rel=0.01)
    # `verbose=None` silencia a barra de progresso; em worker ela poluiria o log
    # a cada turno.
    assert recebido["verbose"] is None
    assert recebido["language"] == "en"
    assert recebido["repo"] == "mlx-community/whisper-small.en-mlx"
    # AMOSTRAS, nunca caminho de arquivo — é o que evita o `ffmpeg` no PATH.
    assert recebido["amostras"] == pytest.approx(2.3 * 16_000, rel=0.01)


async def test_mlx_cai_para_en_quando_a_biblioteca_nao_reporta_lingua(
    audio: AudioInput,
) -> None:
    def transcribe_falso(
        audio_amostras: NDArray[np.float32],
        *,
        path_or_hf_repo: str,
        language: str,
        verbose: bool | None,
    ) -> dict[str, object]:
        return {"text": "ok"}

    adapter = MlxWhisperSpeechToText(transcribe_falso, "repo")

    assert (await adapter.transcribe(audio)).language == "en"
