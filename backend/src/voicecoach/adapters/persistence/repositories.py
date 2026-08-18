"""Repositórios concretos sobre SQLAlchemy (ADR-0004).

Nenhuma destas classes declara que implementa a porta: elas satisfazem o
``Protocol`` de ``application/ports`` **estruturalmente**, por ter os métodos
com a assinatura certa. A verificação acontece no ``mypy``, no ponto em que uma
delas é atribuída a uma variável tipada com a porta — não em runtime.

Nenhum método comita. A transação pertence a quem abriu a sessão (ADR-0004:
unidade de trabalho explícita) — do contrário seria impossível gravar Turn e
Correction atomicamente no mesmo turno (CARD-013).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from voicecoach.adapters.persistence import mappers
from voicecoach.adapters.persistence.models import SessionRow, StudentRow, TurnRow

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    from voicecoach.domain.session import Session
    from voicecoach.domain.student import Student
    from voicecoach.domain.turn import Turn


class RowNotFoundError(LookupError):
    """Pediu-se para atualizar uma linha que não existe.

    Não é erro de domínio (ADR-0017): nenhuma regra de negócio foi violada — o
    chamador pediu para gravar algo que nunca foi inserido, o que é bug de
    orquestração e pertence a esta camada.
    """


class SqlAlchemyStudentRepository:
    """Implementa ``application.ports.repositories.StudentRepository``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, student: Student) -> None:
        self._session.add(mappers.student_to_row(student))

    async def get(self, student_id: UUID) -> Student | None:
        row = await self._session.get(StudentRow, student_id)
        return None if row is None else mappers.student_from_row(row)


class SqlAlchemySessionRepository:
    """Implementa ``application.ports.repositories.SessionRepository``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, session: Session) -> None:
        self._session.add(mappers.session_to_row(session))

    async def get(self, session_id: UUID) -> Session | None:
        row = await self._session.get(SessionRow, session_id)
        return None if row is None else mappers.session_from_row(row)

    async def update(self, session: Session) -> None:
        row = await self._session.get(SessionRow, session.id)
        if row is None:
            message = f"Session {session.id} não existe."
            raise RowNotFoundError(message)
        mappers.apply_session(session, row)


class SqlAlchemyTurnRepository:
    """Implementa ``application.ports.repositories.TurnRepository``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, turn: Turn) -> None:
        self._session.add(mappers.turn_to_row(turn))

    async def get(self, turn_id: UUID) -> Turn | None:
        row = await self._session.get(TurnRow, turn_id)
        return None if row is None else mappers.turn_from_row(row)

    async def update(self, turn: Turn) -> None:
        """Grava o novo estado de um Turn já persistido.

        Precisa existir porque a entidade não é o objeto mapeado: mudá-la em
        memória não sensibiliza sessão nenhuma. É o oposto do change tracking do
        EF Core — aqui, gravar é sempre um pedido explícito.
        """
        row = await self._session.get(TurnRow, turn.id)
        if row is None:
            message = f"Turn {turn.id} não existe."
            raise RowNotFoundError(message)
        mappers.apply_turn(turn, row)
