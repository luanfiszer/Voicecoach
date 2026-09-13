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
from voicecoach.adapters.stt.faster_whisper_adapter import load_faster_whisper
from voicecoach.application.ports.speech_to_text import AudioInput, SpeechToText
from voicecoach.config import Settings, SttProvider

FIXTURE = Path(__file__).parent.parent / "fixtures" / "stt" / "amazing-project.wav"

# ADR-0055/CARD-039: fala real de aluno iniciante misturando português no meio
# de uma conversa em inglês. Sintetizado com `say -v Luciana` (macOS) — mesma
# voz da investigação do ADR-0055, para que os números permaneçam comparáveis.
# O texto: "Não sei como dizer isso em inglês, você pode me ajudar?"
FIXTURE_PT = Path(__file__).parent.parent / "fixtures" / "stt" / "pt-br-curto.wav"

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


@pytest.fixture
def audio_pt() -> AudioInput:
    return AudioInput(data=FIXTURE_PT.read_bytes())


async def test_multilingue_com_deteccao_entende_o_portugues(
    audio_pt: AudioInput,
) -> None:
    # Critério de aceite do CARD-039: configuração DEFAULT (stt_language=None,
    # modelo multilíngue) — o aluno falando português é ENTENDIDO, não
    # traduzido nem descartado como lixo (ADR-0055).
    adapter: SpeechToText = create_speech_to_text(_settings(SttProvider.FASTER_WHISPER))

    resultado = await adapter.transcribe(audio_pt)

    assert resultado.language == "pt"
    texto = resultado.text.lower()
    assert "ingl" in texto or "ajudar" in texto, resultado.text


async def test_stt_language_forcado_governa_mesmo_com_audio_em_portugues(
    audio_pt: AudioInput,
) -> None:
    # Prova que o campo GOVERNA (ADR-0055): o recuo barato para o comportamento
    # antigo é uma linha de `.env`, sem recompilar.
    settings = _settings(SttProvider.FASTER_WHISPER).model_copy(
        update={"stt_language": "en"}
    )
    adapter: SpeechToText = create_speech_to_text(settings)

    resultado = await adapter.transcribe(audio_pt)

    assert resultado.language == "en"


async def test_confidence_separa_a_alucinacao_do_modelo_en_da_transcricao_correta(
    audio_pt: AudioInput,
) -> None:
    # É o teste que PROVA a separação que o CARD-040 vai usar como desfecho
    # "não entendi" (ADR-0057): o `.en` antigo diante de português alucina; o
    # multilíngue com detecção transcreve certo.
    #
    # NÃO é limiar absoluto contra -1,0 (medido: a alucinação do `.en` é
    # NÃO-DETERMINÍSTICA por causa do fallback de temperatura do Whisper — o
    # próprio ADR-0055 já registrava isso). Rodado 5x neste insumo, o `.en`
    # oscilou entre -0,97 e -1,10: em TORNO do limiar fixo, não abaixo dele de
    # forma confiável. Um teste que passa ou falha por sorte não prova nada —
    # comparar RELATIVAMENTE ao modelo novo é robusto a essa variância e prova
    # exatamente o que o card promete: o novo é sempre muito melhor que o
    # antigo. Dívida explícita para o CARD-040 em `docs/medicao-latencia.md`
    # §13.3: o limiar real de confiança precisa ser mais frouxo que -1,0.
    modelo_antigo = load_faster_whisper("small.en", "en")
    modelo_novo = create_speech_to_text(_settings(SttProvider.FASTER_WHISPER))

    resultado_antigo = await modelo_antigo.transcribe(audio_pt)
    resultado_novo = await modelo_novo.transcribe(audio_pt)

    margem = 0.3
    assert resultado_novo.confidence > resultado_antigo.confidence + margem, (
        resultado_antigo,
        resultado_novo,
    )
    assert resultado_novo.confidence > -1.0, resultado_novo


async def test_segments_tem_tempos_crescentes(audio: AudioInput) -> None:
    adapter: SpeechToText = create_speech_to_text(_settings(SttProvider.FASTER_WHISPER))

    resultado = await adapter.transcribe(audio)

    assert len(resultado.segments) >= 1
    fins = [s.end_seconds for s in resultado.segments]
    assert fins == sorted(fins)
