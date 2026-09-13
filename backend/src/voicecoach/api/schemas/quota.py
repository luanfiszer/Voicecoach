"""``GET /v1/students/me/quota`` — o saldo como leitura (CARD-033).

**Nunca falha e nunca expõe dinheiro** (RNF1/RF4): mesmo com o kill switch
ligado, esta rota responde ``200`` — é a tela que EXPLICA a parede, e ela não
pode estar atrás da parede. O corpo nunca traz valor monetário nem teto de
orçamento; ``service_available``/``blocked_reason`` são os únicos fatos sobre
o estado do serviço que o aluno recebe.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from voicecoach.application.use_cases.read_quota_status import (
    BlockedReason,
    QuotaStatus,
)


class QuotaStatusResponse(BaseModel):
    spoken_seconds: float = Field(description="Falado hoje, na janela da cota.")
    quota_spoken_seconds: float = Field(description="O teto comunicado ao aluno.")
    resets_at: datetime = Field(
        description="Instante absoluto da virada — o MESMO do `retry_after` "
        "do 429 de cota (mesma fonte, ADR-0063)."
    )
    service_available: bool = Field(
        description="`false` quando o kill switch do orçamento está ativo."
    )
    blocked_reason: BlockedReason | None = Field(
        default=None,
        description="Por que o aluno não pode falar agora, sem expor "
        "mecânica de custo. `null` quando ele pode.",
    )

    @classmethod
    def de_status(cls, status: QuotaStatus) -> QuotaStatusResponse:
        return cls(
            spoken_seconds=status.spoken.total_seconds(),
            quota_spoken_seconds=status.quota_spoken.total_seconds(),
            resets_at=status.resets_at,
            service_available=status.service_available,
            blocked_reason=status.blocked_reason,
        )
