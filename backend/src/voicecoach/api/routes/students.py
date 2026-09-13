"""``GET /v1/students/me/quota`` — o saldo de cota como leitura (CARD-033).

**``me``, não um id no path.** O aluno vem do token desde o CARD-049
(``requesting_student_id``, ADR-0007). `me` é o nome que sobreviveu à troca:
o que mudou foi de onde o id sai (token em vez de `DEV_STUDENT_ID`), e a URL
do cliente não mudou.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from voicecoach.api.dependencies import (
    delete_account_handler,
    enforce_delete_account_rate_limit,
    read_quota_status_handler,
    requesting_student_id,
)
from voicecoach.api.schemas.quota import QuotaStatusResponse
from voicecoach.application.use_cases.delete_account import (
    DeleteAccount,
    DeleteAccountHandler,
)
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
    status_de_cota = await handler.handle(ReadQuotaStatus(student_id=student_id))
    return QuotaStatusResponse.de_status(status_de_cota)


@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Exclui a própria conta — LGPD e Guideline 5.1.1(v) da App Store",
    dependencies=[Depends(enforce_delete_account_rate_limit)],
)
async def excluir_conta(
    handler: Annotated[DeleteAccountHandler, Depends(delete_account_handler)],
    student_id: Annotated[UUID, Depends(requesting_student_id)],
) -> None:
    """Marca a conta e revoga toda sessão — imediato (CARD-051, ADR-0069).

    **Não apaga nada aqui.** O expurgo físico (áudio, transcrição, correção,
    sessão) é assíncrono, feito pela varredura periódica do worker
    (`PurgeDeletedAccountsHandler`) — este endpoint só garante que, a partir
    da resposta, a conta não consegue mais entrar.
    """
    await handler.handle(DeleteAccount(student_id=student_id))
