"""As duas invariantes da tradução gravada (CARD-036)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from voicecoach.domain.translation import Translation, TranslationTarget

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)


def traducao(*, index: int = 0, text: str = "Qual praia você foi?") -> Translation:
    return Translation(
        turn_id=uuid4(),
        target=TranslationTarget.REPLY,
        index=index,
        text=text,
        model="claude-haiku-4-5-20251001",
        created_at=NOW,
        estimated_cost_usd=Decimal("0.00016000"),
    )


def test_index_negativo_e_recusado() -> None:
    """O índice é 0-based e denso, como em todo lugar deste domínio."""
    with pytest.raises(ValueError, match="index"):
        traducao(index=-1)


@pytest.mark.parametrize("vazio", ["", "   ", "\n"])
def test_texto_vazio_nao_e_traducao(vazio: str) -> None:
    """Gravar vazio faria o aluno pagar por uma linha que não diz nada — e o
    RF4 devolveria esse vazio para sempre, sem nunca tentar de novo."""
    with pytest.raises(ValueError, match="vazio"):
        traducao(text=vazio)


def test_custo_desconhecido_e_permitido_e_diferente_de_zero() -> None:
    """Nulo é "não sabemos precificar"; zero seria "foi de graça" (ADR-0051)."""
    sem_preco = Translation(
        turn_id=uuid4(),
        target=TranslationTarget.CORRECTION,
        index=3,
        text="Use 'at' para um lugar que você visita.",
        model="modelo-que-ninguem-precificou",
        created_at=NOW,
        estimated_cost_usd=None,
    )

    assert sem_preco.estimated_cost_usd is None
