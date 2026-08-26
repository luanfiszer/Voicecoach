"""Composição do adapter do professor (ADR-0030).

Mesmo padrão da fábrica de STT: uma decisão, tomada uma vez, na subida — e o
import do SDK é **local à função**, para que importar este módulo não arraste o
`anthropic` (e o `httpx2` atrás dele) para dentro de um processo que só queria
ler a configuração.
"""

from __future__ import annotations

import logging
from importlib import resources
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from voicecoach.application.ports.teacher_llm import TeacherLlm
    from voicecoach.config import Settings

logger = logging.getLogger(__name__)

# O v1 continua no pacote, intocado, e é o único motivo de esta constante
# existir: o CARD-013 troca o contrato do professor sem eval (Fase 4), então a
# comparação v1 vs. v2 com casos fixos é a única rede — e ela precisa dos dois
# prompts carregáveis lado a lado. Gatilho para apagar o v1: o eval existir.
PROMPT_VERSION = "v2"


def load_teacher_prompt(version: str = PROMPT_VERSION) -> str:
    """Lê o prompt versionado de dentro do pacote.

    `importlib.resources` e não `open(Path(...))` porque o prompt é um recurso
    **empacotado**: ele viaja no wheel junto do módulo. Ler por caminho relativo
    ao arquivo funcionaria no repositório e quebraria em qualquer instalação.
    Não há equivalente exato em C#; o parente é um recurso embutido no assembly.
    """
    pasta = resources.files("voicecoach.adapters.llm.prompts.teacher")
    return (pasta / f"{version}.md").read_text(encoding="utf-8")


def create_teacher_llm(settings: Settings) -> TeacherLlm:
    """Constrói o adapter do professor com o cliente assíncrono do SDK."""
    from anthropic import AsyncAnthropic

    from voicecoach.adapters.llm.anthropic_teacher import AnthropicTeacher

    logger.info(
        "LLM: professor '%s', prompt %s, max_tokens=%d, timeout=%.1fs",
        settings.teacher_model,
        PROMPT_VERSION,
        settings.teacher_max_tokens,
        settings.teacher_timeout_seconds,
    )
    # `type: ignore[arg-type]`: o `_Client` do adapter declara o MÍNIMO que ele
    # consome, e o `AsyncAnthropic` real não casa estruturalmente porque o
    # `stream()` do SDK é uma pilha de overloads com TypedDicts próprios —
    # reproduzir essa assinatura no Protocol amarraria o adapter aos tipos do
    # SDK, que é o acoplamento que o Protocol existe para evitar. A costura é
    # exercitada de verdade pelo teste marcado `slow`, que chama a API real.
    # Gatilho para remover: o SDK publicar um Protocol público de `messages`.
    return AnthropicTeacher(
        AsyncAnthropic(api_key=settings.anthropic_api_key),  # type: ignore[arg-type]
        model=settings.teacher_model,
        system_prompt=load_teacher_prompt(),
        max_tokens=settings.teacher_max_tokens,
        timeout_seconds=settings.teacher_timeout_seconds,
    )
