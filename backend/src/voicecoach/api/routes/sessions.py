"""``POST /v1/sessions`` — abre uma conversa (ADR-0016/0023).

O mínimo que o card pede, e nada além: sem ele o cliente não tem onde falar,
porque todo turn nasce dentro de uma sessão (``Session.start_turn`` é a fábrica).

**O aluno é o ``DEV_STUDENT_ID``, e isso é decisão registrada, não esquecimento.**
Não há autenticação nesta fase (o "Out" do CARD-010 manda auth real para fase
própria, ADR-0007). Quando ela entrar, o que muda aqui é uma linha — o
``student_id`` passa a sair do token em vez da constante — e nada mais, porque
nenhuma outra parte do fluxo pergunta quem é o aluno.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, status

from voicecoach.adapters.persistence.seed import DEV_STUDENT_ID
from voicecoach.api.dependencies import agora, session_repository, unit_of_work
from voicecoach.api.schemas.turns import SessionResponse
from voicecoach.application.ports.repositories import SessionRepository, UnitOfWork
from voicecoach.domain.session import Session

router = APIRouter(tags=["sessions"])


@router.post(
    "/sessions",
    status_code=status.HTTP_201_CREATED,
    summary="Abre uma sessão de conversa",
)
async def criar_sessao(
    sessions: Annotated[SessionRepository, Depends(session_repository)],
    uow: Annotated[UnitOfWork, Depends(unit_of_work)],
    inicio: Annotated[datetime, Depends(agora)],
) -> SessionResponse:
    session = Session(id=uuid4(), student_id=DEV_STUDENT_ID, started_at=inicio)
    await sessions.add(session)
    await uow.commit()
    return SessionResponse(
        id=session.id,
        student_id=session.student_id,
        started_at=session.started_at,
        is_active=session.is_active,
    )
