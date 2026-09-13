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
    start: float = 0.0
    end: float = 1.0
    avg_logprob: float = -0.2
    no_speech_prob: float = 0.01


@dataclass
class _InfoFalsa:
    language: str


class _MotorFalso:
    """Imita o `WhisperModel` no pouco que o adapter usa dele.

    `consumido` registra se alguém chegou a percorrer o generator — é o que
    torna observável a armadilha comentada no adapter.
    """

    def __init__(self, segmentos: list[_SegmentoFalso], language: str = "en") -> None:
        self._segmentos = segmentos
        self._language = language
        self.consumido = False
        self.kwargs_recebidos: dict[str, object] = {}
        self.amostras_recebidas: int | None = None

    def transcribe(
        self,
        audio: NDArray[np.float32],
        /,
        *,
        language: str | None,
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
            yield from self._segmentos

        return gerador(), _InfoFalsa(language=self._language)


@pytest.fixture
def audio() -> AudioInput:
    return AudioInput(data=FIXTURE.read_bytes())


def _motor_de_um_texto(texto: str) -> _MotorFalso:
    return _MotorFalso([_SegmentoFalso(texto)])


async def test_faster_whisper_junta_os_segmentos_num_texto(
    audio: AudioInput,
) -> None:
    motor = _MotorFalso(
        [
            _SegmentoFalso(" Wow, that sounds"),
            _SegmentoFalso(" like an amazing project. "),
        ]
    )
    adapter: SpeechToText = FasterWhisperSpeechToText(motor, language=None)

    resultado = await adapter.transcribe(audio)

    assert resultado.text == "Wow, that sounds like an amazing project."
    assert resultado.language == "en"


async def test_faster_whisper_consome_o_generator(audio: AudioInput) -> None:
    # Se o adapter devolvesse o generator sem percorrê-lo, `text` sairia vazio e
    # o trabalho de CPU aconteceria depois, FORA do executor — no event loop do
    # worker. Esta asserção é o que impede essa regressão de passar batida.
    motor = _motor_de_um_texto("hello")
    adapter = FasterWhisperSpeechToText(motor, language=None)

    await adapter.transcribe(audio)

    assert motor.consumido is True


async def test_faster_whisper_detecta_por_padrao(audio: AudioInput) -> None:
    # ADR-0055: `stt_language=None` (o default de `config.py`) precisa chegar
    # ao motor como `language=None` — é isso que dispara a autodetecção real
    # do `faster-whisper`, não um fallback disfarçado para "en".
    motor = _motor_de_um_texto("ok")

    await FasterWhisperSpeechToText(motor, language=None).transcribe(audio)

    assert motor.kwargs_recebidos["language"] is None


async def test_faster_whisper_forca_o_idioma_quando_configurado(
    audio: AudioInput,
) -> None:
    # O recuo barato do ADR-0055: `stt_language="en"` no `.env`, sem deploy,
    # sem recompilar — e o adapter precisa de fato repassar o valor.
    motor = _motor_de_um_texto("ok")

    await FasterWhisperSpeechToText(motor, language="en").transcribe(audio)

    assert motor.kwargs_recebidos["language"] == "en"


async def test_faster_whisper_usa_os_parametros_medidos(
    audio: AudioInput,
) -> None:
    # Não é preciosismo: `beam_size=5` custa ~30% a mais e `int8` é MAIS lento
    # neste hardware (ADR-0027, itens 5 e 6). Um "ajuste" silencioso aqui
    # devolveria a latência que a medição comprou.
    motor = _motor_de_um_texto("ok")

    await FasterWhisperSpeechToText(motor, language=None).transcribe(audio)

    assert motor.kwargs_recebidos["beam_size"] == 1
    assert motor.kwargs_recebidos["vad_filter"] is True


async def test_faster_whisper_decodifica_os_bytes_antes_de_transcrever(
    audio: AudioInput,
) -> None:
    # O motor recebe AMOSTRAS, não bytes: 2,3 s a 16 kHz.
    motor = _motor_de_um_texto("ok")

    resultado = await FasterWhisperSpeechToText(motor, language=None).transcribe(audio)

    assert motor.amostras_recebidas == pytest.approx(2.3 * 16_000, rel=0.01)
    assert resultado.duration_seconds == pytest.approx(2.3, rel=0.01)


async def test_faster_whisper_monta_segments_com_tempos_do_motor(
    audio: AudioInput,
) -> None:
    # ADR-0056: os `start`/`end` que o Whisper já calcula viram `Segment` do
    # projeto, não o objeto do `faster-whisper`.
    motor = _MotorFalso(
        [
            _SegmentoFalso("Wow,", start=0.0, end=1.0, avg_logprob=-0.1),
            _SegmentoFalso("amazing.", start=1.0, end=2.3, avg_logprob=-0.3),
        ]
    )

    resultado = await FasterWhisperSpeechToText(motor, language=None).transcribe(audio)

    assert [s.start_seconds for s in resultado.segments] == [0.0, 1.0]
    assert [s.end_seconds for s in resultado.segments] == [1.0, 2.3]
    assert [s.text for s in resultado.segments] == ["Wow,", "amazing."]


async def test_faster_whisper_confidence_e_media_ponderada_por_duracao(
    audio: AudioInput,
) -> None:
    # ADR-0056: a média pondera pela DURAÇÃO de cada segmento, não pela
    # contagem — um segmento de 1s pesa metade de um de 2s.
    motor = _MotorFalso(
        [
            _SegmentoFalso("a", start=0.0, end=1.0, avg_logprob=-0.1),
            _SegmentoFalso("b", start=1.0, end=3.0, avg_logprob=-0.4),
        ]
    )

    resultado = await FasterWhisperSpeechToText(motor, language=None).transcribe(audio)

    esperado = (-0.1 * 1.0 + -0.4 * 2.0) / 3.0
    assert resultado.confidence == pytest.approx(esperado)


async def test_faster_whisper_confidence_zero_sem_segmentos(
    audio: AudioInput,
) -> None:
    motor = _MotorFalso([])

    resultado = await FasterWhisperSpeechToText(motor, language=None).transcribe(audio)

    assert resultado.confidence == 0.0
    assert resultado.no_speech == 0.0
    assert resultado.segments == ()


async def test_faster_whisper_no_speech_e_o_maior_entre_os_segmentos(
    audio: AudioInput,
) -> None:
    motor = _MotorFalso(
        [
            _SegmentoFalso("a", no_speech_prob=0.02),
            _SegmentoFalso("b", no_speech_prob=0.55),
            _SegmentoFalso("c", no_speech_prob=0.10),
        ]
    )

    resultado = await FasterWhisperSpeechToText(motor, language=None).transcribe(audio)

    assert resultado.no_speech == pytest.approx(0.55)


async def test_mlx_extrai_texto_e_duracao(audio: AudioInput) -> None:
    recebido: dict[str, object] = {}

    def transcribe_falso(
        audio_amostras: NDArray[np.float32],
        *,
        path_or_hf_repo: str,
        language: str | None,
        verbose: bool | None,
    ) -> dict[str, object]:
        recebido["repo"] = path_or_hf_repo
        recebido["language"] = language
        recebido["verbose"] = verbose
        recebido["amostras"] = len(audio_amostras)
        return {
            "text": "  Wow, that sounds like an amazing project.  ",
            "language": "en",
            "segments": [],
        }

    adapter: SpeechToText = MlxWhisperSpeechToText(
        transcribe_falso, "mlx-community/whisper-small-mlx", language=None
    )

    resultado = await adapter.transcribe(audio)

    assert resultado.text == "Wow, that sounds like an amazing project."
    assert resultado.duration_seconds == pytest.approx(2.3, rel=0.01)
    # `verbose=None` silencia a barra de progresso; em worker ela poluiria o log
    # a cada turno.
    assert recebido["verbose"] is None
    # `None` chega intacto — é o que dispara a autodetecção real do motor
    # multilíngue (verificado em `mlx_whisper/transcribe.py`, ADR-0055).
    assert recebido["language"] is None
    assert recebido["repo"] == "mlx-community/whisper-small-mlx"
    # AMOSTRAS, nunca caminho de arquivo — é o que evita o `ffmpeg` no PATH.
    assert recebido["amostras"] == pytest.approx(2.3 * 16_000, rel=0.01)


async def test_mlx_forca_o_idioma_quando_configurado(audio: AudioInput) -> None:
    recebido: dict[str, object] = {}

    def transcribe_falso(
        audio_amostras: NDArray[np.float32],
        *,
        path_or_hf_repo: str,
        language: str | None,
        verbose: bool | None,
    ) -> dict[str, object]:
        recebido["language"] = language
        return {"text": "ok", "language": "en", "segments": []}

    adapter = MlxWhisperSpeechToText(transcribe_falso, "repo", language="en")

    await adapter.transcribe(audio)

    assert recebido["language"] == "en"


async def test_mlx_usa_o_idioma_que_a_biblioteca_devolveu(audio: AudioInput) -> None:
    # Ao contrário do adapter antigo (que caía para "en" quando faltava a
    # chave), agora o valor vem sempre de `saida["language"]` — a biblioteca
    # sempre a devolve, detectada ou forçada (verificado em transcribe.py).
    def transcribe_falso(
        audio_amostras: NDArray[np.float32],
        *,
        path_or_hf_repo: str,
        language: str | None,
        verbose: bool | None,
    ) -> dict[str, object]:
        return {"text": "ok", "language": "pt", "segments": []}

    adapter = MlxWhisperSpeechToText(transcribe_falso, "repo", language=None)

    assert (await adapter.transcribe(audio)).language == "pt"


async def test_mlx_monta_segments_e_confidence_a_partir_do_dict(
    audio: AudioInput,
) -> None:
    # ADR-0056: os segmentos do `mlx-whisper` vêm como lista de `dict`, e
    # nenhum desses dicts pode sobreviver até `application` — só `Segment`.
    def transcribe_falso(
        audio_amostras: NDArray[np.float32],
        *,
        path_or_hf_repo: str,
        language: str | None,
        verbose: bool | None,
    ) -> dict[str, object]:
        return {
            "text": "a b",
            "language": "en",
            "segments": [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "a",
                    "avg_logprob": -0.1,
                    "no_speech_prob": 0.02,
                },
                {
                    "start": 1.0,
                    "end": 3.0,
                    "text": "b",
                    "avg_logprob": -0.4,
                    "no_speech_prob": 0.55,
                },
            ],
        }

    adapter = MlxWhisperSpeechToText(transcribe_falso, "repo", language=None)

    resultado = await adapter.transcribe(audio)

    assert [s.start_seconds for s in resultado.segments] == [0.0, 1.0]
    assert [s.end_seconds for s in resultado.segments] == [1.0, 3.0]
    esperado = (-0.1 * 1.0 + -0.4 * 2.0) / 3.0
    assert resultado.confidence == pytest.approx(esperado)
    assert resultado.no_speech == pytest.approx(0.55)


async def test_mlx_confidence_zero_sem_segmentos(audio: AudioInput) -> None:
    def transcribe_falso(
        audio_amostras: NDArray[np.float32],
        *,
        path_or_hf_repo: str,
        language: str | None,
        verbose: bool | None,
    ) -> dict[str, object]:
        return {"text": "", "language": "en", "segments": []}

    adapter = MlxWhisperSpeechToText(transcribe_falso, "repo", language=None)

    resultado = await adapter.transcribe(audio)

    assert resultado.confidence == 0.0
    assert resultado.no_speech == 0.0
    assert resultado.segments == ()
