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
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, status

from voicecoach.adapters.persistence.seed import DEV_STUDENT_ID
from voicecoach.api.dependencies import (
    agora,
    end_session_handler,
    session_repository,
    unit_of_work,
)
from voicecoach.api.errors import ProblemError
from voicecoach.api.schemas.problem import TYPE_SESSION_NOT_FOUND
from voicecoach.api.schemas.turns import SessionResponse, SessionSummaryResponse
from voicecoach.application.ports.repositories import SessionRepository, UnitOfWork
from voicecoach.application.result import Err, Ok
from voicecoach.application.use_cases.end_session import (
    EndSession,
    EndSessionHandler,
    SessionNotFound,
)
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


@router.post(
    "/sessions/{session_id}/end",
    summary="Encerra a sessão e devolve o resumo pós-sessão",
)
async def encerrar_sessao(
    session_id: UUID,
    handler: Annotated[EndSessionHandler, Depends(end_session_handler)],
) -> SessionSummaryResponse:
    """Idempotente (RF2): chamar de novo numa sessão já encerrada devolve o
    mesmo resumo, não um erro — ver o docstring de ``EndSessionHandler``.
    """
    resultado = await handler.handle(EndSession(session_id=session_id))
    match resultado:
        case Ok(value=resumo):
            return SessionSummaryResponse.de_resumo(resumo)
        case Err(error=SessionNotFound(session_id=inexistente)):
            raise ProblemError(
                type_=TYPE_SESSION_NOT_FOUND,
                title="Sessão não encontrada",
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Nenhuma sessão com este id.",
                session_id=str(inexistente),
            )
