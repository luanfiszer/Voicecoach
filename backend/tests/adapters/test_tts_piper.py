"""Adapter de TTS: codificação sempre, motor real só sob `-m slow`.

**A diferença em relação ao marker `slow` do CARD-007 importa e está aqui de
propósito:** lá ele significava "gasta dinheiro" (chamada paga à Anthropic).
Aqui ele custa **tempo de CPU e um download de voz de 60 MB** — nada de conta a
pagar (ADR-0010). Quem decide rodar precisa saber qual dos dois custos está
aceitando.
"""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

import pytest
from faster_whisper.audio import decode_audio

from voicecoach.adapters.tts.encoding import (
    CONTENT_TYPE,
    EXTENSION,
    AacAudioEncoder,
    to_aac,
)
from voicecoach.adapters.tts.factory import (
    TtsProviderUnavailableError,
    create_text_to_speech,
)
from voicecoach.adapters.tts.piper_adapter import TtsVoiceNotFoundError, load_piper
from voicecoach.application.ports.audio_encoder import AudioEncoder, AudioEncodingError
from voicecoach.application.ports.text_to_speech import (
    BYTES_PER_SAMPLE,
    SynthesizedAudio,
    TextToSpeech,
    concat,
)
from voicecoach.config import Settings, TtsProvider

TAXA = 22_050
VOICES_DIR = Path(__file__).resolve().parents[2] / "voices"
VOZ = "en_US-lessac-medium"

# Nem toda máquina tem a voz baixada; `slow` já os deseleciona, mas o skip dá a
# mensagem certa a quem rodar `-m slow` numa máquina limpa.
sem_voz = pytest.mark.skipif(
    not (VOICES_DIR / f"{VOZ}.onnx").exists(),
    reason=f"voz {VOZ} não baixada em {VOICES_DIR} (ver backend/README.md)",
)


def pcm_senoide(segundos: float, taxa: int = TAXA) -> bytes:
    """Um tom audível — silêncio puro comprime a quase nada e não provaria nada."""
    import math

    amostras = int(segundos * taxa)
    return b"".join(
        int(16000 * math.sin(2 * math.pi * 440 * i / taxa)).to_bytes(
            BYTES_PER_SAMPLE, "little", signed=True
        )
        for i in range(amostras)
    )


# -- codificação: roda sempre, não precisa de modelo -------------------------


def test_aac_comprime_o_pcm_varias_vezes() -> None:
    audio = SynthesizedAudio(pcm=pcm_senoide(3.0), sample_rate=TAXA)

    comprimido = to_aac(audio)

    assert len(comprimido) < len(audio.pcm) / 3
    assert CONTENT_TYPE == "audio/aac"
    assert EXTENSION == "aac"


def test_aac_gerado_e_decodificavel_e_preserva_a_duracao() -> None:
    """O arquivo tem de TOCAR, não só existir.

    A tolerância de 100 ms não é folga arbitrária: o encoder AAC acrescenta um
    *priming* de algumas dezenas de milissegundos no início do fluxo. Medido
    aqui: ~70 ms num áudio de 4,16 s. É inaudível e é o preço do formato — o que
    não se pode aceitar é a diferença crescer com o tamanho, o que indicaria
    perda de quadros no fim (o `encode(None)` esquecido).
    """
    audio = SynthesizedAudio(pcm=pcm_senoide(4.0), sample_rate=TAXA)

    amostras = decode_audio(__import__("io").BytesIO(to_aac(audio)))

    # `decode_audio` reamostra para 16 kHz — a taxa do Whisper, não a nossa.
    duracao = len(amostras) / 16_000
    assert duracao == pytest.approx(audio.duration_seconds, abs=0.1)


def test_full_concatenado_dura_a_soma_e_ainda_toca() -> None:
    """Critério de aceite do card, do PCM ao arquivo final."""
    partes = [
        SynthesizedAudio(pcm=pcm_senoide(d), sample_rate=TAXA) for d in (1.2, 0.8, 2.0)
    ]

    inteiro = concat(partes)
    amostras = decode_audio(__import__("io").BytesIO(to_aac(inteiro)))

    assert len(amostras) / 16_000 == pytest.approx(4.0, abs=0.1)


# -- fábrica: também não precisa de modelo -----------------------------------


async def test_o_encoder_satisfaz_a_porta_e_rotula_o_que_grava() -> None:
    """O adapter que o CARD-009 precisou criar para comprimir sem quebrar camada.

    `content_type` e `extension` saem do **mesmo lugar** (o codec) para que não
    possam divergir: gravar `.aac` com `audio/mpeg` é o tipo de erro que só
    aparece no aparelho de alguém.
    """
    porta: AudioEncoder = AacAudioEncoder()
    audio = SynthesizedAudio(pcm=pcm_senoide(0.3), sample_rate=TAXA)

    codificado = await porta.encode(audio)

    assert codificado.content_type == "audio/aac"
    assert codificado.extension == "aac"
    assert 0 < len(codificado.data) < len(audio.pcm)


async def test_o_encoder_nao_bloqueia_o_event_loop() -> None:
    """Mesma lição do CARD-008 (Q11), agora no codec.

    Codificar é CPU-bound. Um `to_aac` chamado direto da corrotina congelaria o
    event loop exatamente no intervalo em que a próxima sentença deveria estar
    sendo sintetizada — e num turno de 6 trechos isso acontece 6 vezes.
    """
    voltas = 0

    async def heartbeat() -> None:
        nonlocal voltas
        while True:
            await asyncio.sleep(0.001)
            voltas += 1

    batedor = asyncio.create_task(heartbeat())
    # Áudio grande o bastante para a codificação demorar mais que uma volta.
    audio = SynthesizedAudio(pcm=pcm_senoide(20.0), sample_rate=TAXA)
    await AacAudioEncoder().encode(audio)
    batedor.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await batedor

    assert voltas > 0


async def test_pcm_invalido_atravessa_como_erro_da_porta() -> None:
    """Exceção do PyAV não pode vazar para `application`."""
    quebrado = SynthesizedAudio(pcm=pcm_senoide(0.1), sample_rate=TAXA)
    object.__setattr__(quebrado, "pcm", b"\x00" * 7)

    with pytest.raises(AudioEncodingError):
        await AacAudioEncoder().encode(quebrado)


def test_kokoro_falha_na_subida_em_vez_de_existir_pela_metade() -> None:
    """Fallback silencioso é proibido (ADR-0027, item 3), e o mesmo vale aqui."""
    settings = Settings(  # type: ignore[call-arg]
        anthropic_api_key="x", tts_provider=TtsProvider.KOKORO, _env_file=None
    )

    with pytest.raises(TtsProviderUnavailableError, match="dependências de sistema"):
        create_text_to_speech(settings)


def test_voz_ausente_falha_na_subida_dizendo_como_resolver() -> None:
    """O erro tem de carregar o comando que o conserta."""
    with pytest.raises(TtsVoiceNotFoundError, match="download_voices"):
        load_piper(Path("/tmp/nao-existe"), "en_US-inexistente")


# -- motor real --------------------------------------------------------------


@pytest.mark.slow
@sem_voz
async def test_o_adapter_satisfaz_a_porta_e_sintetiza() -> None:
    porta: TextToSpeech = load_piper(VOICES_DIR, VOZ)

    audio = await porta.synthesize("That's a great point.")

    assert audio.sample_rate == TAXA
    assert audio.duration_seconds > 0.3
    assert len(audio.pcm) % BYTES_PER_SAMPLE == 0


@pytest.mark.slow
@sem_voz
async def test_uma_chamada_por_sentenca_e_mais_barata_que_o_texto_inteiro() -> None:
    """A forma da porta compra latência, e o teste mostra o número.

    O RTF é constante (~0,024), então cortar em frases não desperdiça nada: a
    primeira frase fica pronta numa fração do tempo da resposta completa. É a
    premissa da cascata (ADR-0023) verificada contra o motor de verdade.
    """
    tts = load_piper(VOICES_DIR, VOZ)
    primeira = "That's a great point."
    inteiro = (
        "That's a great point. Working in a hospital must be really demanding, "
        "especially during long shifts. Have you found any way to relax?"
    )

    audio_primeira = await tts.synthesize(primeira)
    audio_inteiro = await tts.synthesize(inteiro)

    assert audio_primeira.duration_seconds < audio_inteiro.duration_seconds / 2
