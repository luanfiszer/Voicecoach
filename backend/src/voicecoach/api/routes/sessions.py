"""``POST /v1/sessions`` — abre uma conversa (ADR-0016/0023).

O mínimo que o card pede, e nada além: sem ele o cliente não tem onde falar,
porque todo turn nasce dentro de uma sessão (``Session.start_turn`` é a fábrica).

**O aluno vem do token, desde o CARD-049.** Antes disso era sempre
``DEV_STUDENT_ID`` — a troca foi exatamente a linha única que o comentário
antigo previa (ADR-0007): ``requesting_student_id`` passou a decodificar o
``Bearer``, e nada mais aqui mudou.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, status

from voicecoach.api.dependencies import (
    agora,
    end_session_handler,
    list_sessions_handler,
    requesting_student_id,
    session_repository,
    unit_of_work,
)
from voicecoach.api.errors import ProblemError
from voicecoach.api.schemas.problem import TYPE_SESSION_NOT_FOUND
from voicecoach.api.schemas.sessions import SessionListEntry, SessionListResponse
from voicecoach.api.schemas.turns import SessionResponse, SessionSummaryResponse
from voicecoach.application.ports.repositories import SessionRepository, UnitOfWork
from voicecoach.application.result import Err, Ok
from voicecoach.application.use_cases.end_session import (
    EndSession,
    EndSessionHandler,
    SessionNotFound,
)
from voicecoach.application.use_cases.list_sessions import (
    ListSessions,
    ListSessionsHandler,
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
    student_id: Annotated[UUID, Depends(requesting_student_id)],
) -> SessionResponse:
    session = Session(id=uuid4(), student_id=student_id, started_at=inicio)
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


# A janela default é a promessa da tela: *"sessões anteriores a 30 dias vivem
# no app web"* (RF2). Constante de módulo e não número solto na assinatura para
# que o schema do OpenAPI e a documentação digam o mesmo valor.
JANELA_PADRAO_EM_DIAS = 30
JANELA_MAXIMA_EM_DIAS = 365


@router.get(
    "/sessions",
    summary="As sessões do aluno, da mais recente para a mais antiga",
)
async def listar_sessoes(
    handler: Annotated[ListSessionsHandler, Depends(list_sessions_handler)],
    student_id: Annotated[UUID, Depends(requesting_student_id)],
    days: Annotated[
        int,
        Query(
            ge=1,
            le=JANELA_MAXIMA_EM_DIAS,
            description="Janela em dias. O que ficou fora dela não é erro, "
            "é ausência — a tela promete que o histórico longo vive na web.",
        ),
    ] = JANELA_PADRAO_EM_DIAS,
) -> SessionListResponse:
    """Leitura pura: não gasta cota e responde `200` mesmo com a cota estourada.

    Aluno sem sessão nenhuma recebe `sessions: []` (RF5) — ausência de sessões
    é uma resposta, não um recurso que não existe.
    """
    itens = await handler.handle(
        ListSessions(student_id=student_id, window=timedelta(days=days))
    )
    return SessionListResponse(
        sessions=[SessionListEntry.de_item(item) for item in itens],
        window_days=days,
    )
