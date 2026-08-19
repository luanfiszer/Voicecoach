"""Escolha do adapter de STT no boot (ADR-0027, itens 2 e 3).

Uma decisão, tomada uma vez, na subida — nunca por job. Latência que varia sem
que ninguém saiba por quê é o oposto do que um alvo medido exige.
"""

from __future__ import annotations

import logging
import platform
import sys
from typing import TYPE_CHECKING

from voicecoach.config import SttProvider

if TYPE_CHECKING:
    from voicecoach.application.ports.speech_to_text import SpeechToText
    from voicecoach.config import Settings

logger = logging.getLogger(__name__)


class SttProviderUnavailableError(RuntimeError):
    """A escolha explícita de `STT_PROVIDER` não é executável nesta máquina.

    Herda de ``RuntimeError`` e **não** de ``DomainError``: não é invariante de
    negócio violada (ADR-0017), é configuração impossível de satisfazer. O lugar
    dela é a subida do processo, onde ninguém a captura.
    """


def is_apple_silicon() -> bool:
    """Mac com processador ARM — a única plataforma onde o ``mlx`` existe."""
    return sys.platform == "darwin" and platform.machine() == "arm64"


def resolve_stt_provider(configured: SttProvider) -> SttProvider:
    """Traduz a configuração no adapter que de fato vai rodar.

    Devolve sempre um provider **concreto**: ``auto`` nunca sai daqui.

    Uma escolha explícita incompatível **levanta**, não cai para o outro
    adapter (ADR-0027, item 3). O fallback silencioso seria confortável e
    esconderia uma regressão de 2x de latência atrás de uma linha de log —
    a mesma classe de falha que os ADRs 0021 e 0022 rejeitaram.
    """
    if configured is SttProvider.OPENAI:
        # O enum carrega o valor porque o ADR-0011 prevê o modo qualidade, mas
        # o adapter não existe: o ADR-0010 restringe gasto ao Claude, então uma
        # implementação aqui seria código que nunca pode ser exercitado.
        raise NotImplementedError(
            "STT_PROVIDER=openai ainda não tem adapter: o ADR-0010 restringe "
            "gasto de API ao Claude. Use 'auto', 'mlx' ou 'faster_whisper'."
        )

    apple_silicon = is_apple_silicon()

    if configured is SttProvider.AUTO:
        resolvido = SttProvider.MLX if apple_silicon else SttProvider.FASTER_WHISPER
        logger.info(
            "STT: STT_PROVIDER=auto resolvido para '%s' (plataforma %s/%s)",
            resolvido.value,
            sys.platform,
            platform.machine(),
        )
        return resolvido

    if configured is SttProvider.MLX and not apple_silicon:
        raise SttProviderUnavailableError(
            f"STT_PROVIDER=mlx exige Apple Silicon, mas esta máquina é "
            f"{sys.platform}/{platform.machine()}. O mlx-whisper não roda aqui. "
            f"Use STT_PROVIDER=faster_whisper, ou 'auto' para resolver pela "
            f"plataforma."
        )

    logger.info("STT: adapter '%s' escolhido por configuração", configured.value)
    return configured


def create_speech_to_text(settings: Settings) -> SpeechToText:
    """Resolve o provider e carrega o modelo — a composição, com o custo junto.

    Chamada uma vez na subida do worker (CARD-009, ADR-0025). A carga dos pesos
    acontece aqui dentro, e é ela que custa 36-99 s na primeira execução de uma
    máquina limpa.

    Os imports dos adapters são locais à função pelo mesmo motivo do import
    tardio do ``mlx``: importar este módulo não deve arrastar biblioteca de IA
    nenhuma para dentro do processo.
    """
    provider = resolve_stt_provider(settings.stt_provider)

    if provider is SttProvider.MLX:
        from voicecoach.adapters.stt.mlx_whisper_adapter import load_mlx_whisper

        logger.info("STT: carregando modelo mlx '%s'", settings.stt_model_mlx)
        return load_mlx_whisper(settings.stt_model_mlx)

    from voicecoach.adapters.stt.faster_whisper_adapter import (
        load_faster_whisper,
    )

    logger.info(
        "STT: carregando modelo faster-whisper '%s'",
        settings.stt_model_faster_whisper,
    )
    return load_faster_whisper(settings.stt_model_faster_whisper)
