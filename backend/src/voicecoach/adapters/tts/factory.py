"""Escolha do adapter de TTS no boot — o padrão das fábricas de STT e LLM.

Uma decisão, tomada uma vez, na subida. Os imports dos adapters são **locais à
função**: importar esta fábrica não pode arrastar motor de voz nenhum para
dentro do processo (o `import kokoro` sozinho custa 2,45 s).

Diferença em relação à fábrica de STT: **não há `auto` aqui**. Lá a escolha
dependia da plataforma (`mlx` só existe em Apple Silicon) e resolver no boot era
a única saída honesta. O Piper roda igual nos quatro alvos que publica wheel, e
"resolva sozinho" seria indireção sem pergunta a responder.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from voicecoach.config import TtsProvider

if TYPE_CHECKING:
    from voicecoach.application.ports.text_to_speech import TextToSpeech
    from voicecoach.config import Settings

logger = logging.getLogger(__name__)


class TtsProviderUnavailableError(RuntimeError):
    """O motor pedido não é executável neste ambiente.

    Como o `SttProviderUnavailableError`, mora no adapter e não na porta: é erro
    de subida, e ninguém o captura (ADR-0031, item 5 — onde o erro mora é
    consequência de quem precisa capturá-lo).
    """


def create_text_to_speech(settings: Settings) -> TextToSpeech:
    """Resolve o motor e carrega a voz — a composição, com o custo junto.

    Chamada uma vez na subida do worker (ADR-0025). A carga acontece aqui
    dentro: 0,43 s no Piper, 3,21 s no Kokoro.
    """
    if settings.tts_provider is TtsProvider.KOKORO:
        # O Kokoro continua no enum porque a medição pode ser refeita em outra
        # máquina, mas ele NÃO é instalado por default: exige `espeak-ng` de
        # sistema, o conserto do `EspeakWrapper` depois do import, e o modelo
        # `en_core_web_sm` do spaCy (§4.3). Implementar o adapter sem essas três
        # coisas resolvidas seria código que nunca roda — a mesma razão pela
        # qual `STT_PROVIDER=openai` levanta em vez de existir pela metade.
        raise TtsProviderUnavailableError(
            "TTS_PROVIDER=kokoro não tem adapter: o Kokoro exige três "
            "dependências de sistema (espeak-ng, o reaponte do EspeakWrapper e "
            "o en_core_web_sm do spaCy) que o CARD-008 mediu e recusou. "
            "Use 'piper', ou reabra a decisão com um ADR novo."
        )

    from voicecoach.adapters.tts.piper_adapter import load_piper

    logger.info(
        "TTS: carregando voz piper '%s' de '%s'",
        settings.tts_voice,
        settings.tts_voices_dir,
    )
    return load_piper(settings.tts_voices_dir, settings.tts_voice)
