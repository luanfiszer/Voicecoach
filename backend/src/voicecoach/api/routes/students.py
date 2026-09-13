"""``GET /v1/students/me/quota`` — o saldo de cota como leitura (CARD-033).

**``me``, não um id no path.** O mesmo `DEV_STUDENT_ID` que `POST /sessions`
já usa (`api/routes/sessions.py`) — não há autenticação nesta fase (ADR-0007).
`me` é o nome que sobrevive à troca: quando a auth entrar, o que muda é de
onde o id sai (token em vez de constante), e a URL do cliente não muda.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from voicecoach.adapters.persistence.seed import DEV_STUDENT_ID
from voicecoach.api.dependencies import read_quota_status_handler
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
) -> QuotaStatusResponse:
    """Nunca recusa (RNF1): kill switch ativo ou cota estourada respondem
    `200` — é a tela que EXPLICA a parede, e ela não pode estar atrás dela.
    """
    status = await handler.handle(ReadQuotaStatus(student_id=DEV_STUDENT_ID))
    return QuotaStatusResponse.de_status(status)
