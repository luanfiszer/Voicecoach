"""``GET /v1/students/me/quota`` — o saldo de cota como leitura (CARD-033).

**``me``, não um id no path.** O aluno vem do token desde o CARD-049
(``requesting_student_id``, ADR-0007). `me` é o nome que sobreviveu à troca:
o que mudou foi de onde o id sai (token em vez de `DEV_STUDENT_ID`), e a URL
do cliente não mudou.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from voicecoach.api.dependencies import read_quota_status_handler, requesting_student_id
from voicecoach.api.schemas.quota import QuotaStatusResponse
from voicecoach.application.use_cases.read_quota_status import (
    ReadQuotaStatus,
    ReadQuotaStatusHandler,
)

router = APIRouter(prefix="/students", tags=["students"])


@router.get(
    "/me/quota",
    summary="O saldo de cota e o estado do serviço, como leitura",
)
async def ler_cota(
    handler: Annotated[ReadQuotaStatusHandler, Depends(read_quota_status_handler)],
    student_id: Annotated[UUID, Depends(requesting_student_id)],
) -> QuotaStatusResponse:
    """Nunca recusa (RNF1): kill switch ativo ou cota estourada respondem
    `200` — é a tela que EXPLICA a parede, e ela não pode estar atrás dela.
    """
    status = await handler.handle(ReadQuotaStatus(student_id=student_id))
    return QuotaStatusResponse.de_status(status)
