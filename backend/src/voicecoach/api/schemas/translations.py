"""Contrato HTTP da tradução sob demanda (CARD-036).

**O corpo do POST não tem campo de texto**, e a ausência é a decisão de
segurança do RF1: o cliente diz QUAL texto do produto quer em português, nunca
manda o texto. Um `text: str` aqui transformaria o endpoint num proxy de LLM
aberto pago por nós — o primeiro risco que o card nomeia.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from voicecoach.domain.translation import TranslationTarget


class TranslationRequest(BaseModel):
    """Qual texto do turn traduzir."""

    target: TranslationTarget = Field(
        description="`reply` é a resposta do professor; `correction` é a "
        "explicação de uma correção."
    )
    index: int = Field(
        default=0,
        ge=0,
        description="Ignorado para `reply` (há uma resposta por turn); para "
        "`correction`, é o índice 0-based na lista de correções do turn.",
    )


class TranslationResponse(BaseModel):
    """O texto em português."""

    text: str
    cached: bool = Field(
        description="`true` quando a tradução já existia e nada foi cobrado. "
        "O corpo é o mesmo nos dois casos — o campo torna o 'não paga duas "
        "vezes' observável de fora."
    )
