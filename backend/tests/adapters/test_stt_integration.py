"""Os adapters contra os modelos REAIS — o único teste que prova que transcrevem.

Marcado `slow` e **deselecionado por padrão** (`addopts` do pyproject): baixa
pesos na primeira execução de uma máquina limpa (36-99 s medidos) e o caminho
`mlx` não existe no CI, que roda em x86.

    uv run pytest -m slow

Essa assimetria de cobertura é registrada e aceita no ADR-0027, não resolvida:
o CI cobre o caminho `faster-whisper`; o caminho `mlx` depende desta execução
local. Fingir o contrário seria pior que admitir.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from voicecoach.adapters.stt.factory import create_speech_to_text, is_apple_silicon
from voicecoach.application.ports.speech_to_text import AudioInput, SpeechToText
from voicecoach.config import Settings, SttProvider

FIXTURE = Path(__file__).parent.parent / "fixtures" / "stt" / "amazing-project.wav"

# O insumo diz "Wow, that sounds like an amazing project." Asserção por
# palavra-chave, não por igualdade: exigir a string exata transformaria
# qualquer diferença de pontuação entre os dois modelos em falha de teste, e a
# pergunta aqui é "transcreveu?", não "transcreveu idêntico?".
PALAVRAS_CHAVE = ("amazing", "project")

pytestmark = pytest.mark.slow


@pytest.fixture
def audio() -> AudioInput:
    return AudioInput(data=FIXTURE.read_bytes())


def _settings(provider: SttProvider) -> Settings:
    return Settings(  # type: ignore[call-arg]  # o pydantic preenche do ambiente
        anthropic_api_key="test-key",
        stt_provider=provider,
        _env_file=None,
    )


async def test_faster_whisper_transcreve_o_insumo_conhecido(
    audio: AudioInput,
) -> None:
    adapter: SpeechToText = create_speech_to_text(_settings(SttProvider.FASTER_WHISPER))

    resultado = await adapter.transcribe(audio)

    texto = resultado.text.lower()
    assert all(palavra in texto for palavra in PALAVRAS_CHAVE), resultado.text
    assert resultado.language == "en"
    assert resultado.duration_seconds == pytest.approx(2.3, rel=0.01)


@pytest.mark.skipif(
    not is_apple_silicon(), reason="mlx-whisper só existe em Apple Silicon"
)
async def test_mlx_transcreve_o_mesmo_insumo(audio: AudioInput) -> None:
    adapter: SpeechToText = create_speech_to_text(_settings(SttProvider.MLX))

    resultado = await adapter.transcribe(audio)

    texto = resultado.text.lower()
    assert all(palavra in texto for palavra in PALAVRAS_CHAVE), resultado.text
    assert resultado.duration_seconds == pytest.approx(2.3, rel=0.01)


@pytest.mark.skipif(
    not is_apple_silicon(), reason="o default `auto` só escolhe mlx em Apple Silicon"
)
async def test_auto_produz_um_adapter_utilizavel_nesta_maquina(
    audio: AudioInput,
) -> None:
    # O caminho que o worker vai percorrer de verdade (CARD-009): config no
    # default, plataforma decidindo.
    adapter: SpeechToText = create_speech_to_text(_settings(SttProvider.AUTO))

    resultado = await adapter.transcribe(audio)

    assert all(palavra in resultado.text.lower() for palavra in PALAVRAS_CHAVE)
