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

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from voicecoach.adapters.persistence import mappers
from voicecoach.adapters.persistence.models import SessionRow, StudentRow, TurnRow
from voicecoach.domain.turn import TurnStatus

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
    """Implementa ``application.ports.repositories.TurnRepository``.

    **Toda leitura de ``TurnRow`` carrega os trechos junto** (ADR-0023). Não é
    otimização: no SQLAlchemy async **não existe lazy loading**. Quem carregasse
    a linha sem pedir a coleção receberia um `Turn` que estoura ao ser mapeado —
    `MissingGreenlet`, ou o `InvalidRequestError` explícito do
    `lazy="raise_on_sql"` declarado no modelo.

    É o contraste que morde para quem vem do EF Core: lá, esquecer o
    ``.Include()`` custa um SELECT N+1 silencioso e o código continua correto.
    Aqui, esquecer é erro em runtime — o que é pior de descobrir e melhor de
    ter descoberto, porque carregamento vira decisão explícita por caso de uso
    em vez de default herdado.
    """

    # `selectinload` emite um SELECT extra com `WHERE turn_id IN (...)`, em vez
    # do JOIN do `joinedload`. Para coleção é a escolha certa: o JOIN
    # multiplicaria as colunas do turn por trecho (produto cartesiano) e o
    # `order_by` do relationship teria que competir com a ordenação da query.
    _COM_TRECHOS = selectinload(TurnRow.audio_chunks)

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, turn: Turn) -> None:
        self._session.add(mappers.turn_to_row(turn))

    async def get(self, turn_id: UUID) -> Turn | None:
        row = await self._session.get(TurnRow, turn_id, options=[self._COM_TRECHOS])
        return None if row is None else mappers.turn_from_row(row)

    async def get_by_idempotency_key(self, key: str) -> Turn | None:
        """Busca pelo índice único parcial ``ix_turns_idempotency_key``.

        O eager load dos trechos vem junto pelo mesmo motivo do ``get``: sem
        ele o mapeador estoura ao tocar a coleção (``lazy="raise_on_sql"``).
        """
        stmt = (
            select(TurnRow)
            .where(TurnRow.idempotency_key == key)
            .options(self._COM_TRECHOS)
        )
        row = (await self._session.scalars(stmt)).one_or_none()
        return None if row is None else mappers.turn_from_row(row)

    async def update(self, turn: Turn) -> None:
        """Grava o novo estado de um Turn já persistido.

        Precisa existir porque a entidade não é o objeto mapeado: mudá-la em
        memória não sensibiliza sessão nenhuma. É o oposto do change tracking do
        EF Core — aqui, gravar é sempre um pedido explícito.

        O eager load é tão obrigatório aqui quanto no ``get``: ``apply_turn``
        precisa comparar os trechos já gravados com os da entidade para saber
        quais acrescentar.
        """
        row = await self._session.get(TurnRow, turn.id, options=[self._COM_TRECHOS])
        if row is None:
            message = f"Turn {turn.id} não existe."
            raise RowNotFoundError(message)
        mappers.apply_turn(turn, row)

    async def list_by_session(self, session_id: UUID, *, limit: int) -> list[Turn]:
        """Os últimos ``limit`` turnos concluídos da sessão, em ordem cronológica.

        **A query ordena ao contrário do resultado, e isso é o ponto.** Para
        pegar os N mais RECENTES é preciso ordenar decrescente e cortar; para
        montar o histórico do professor é preciso a ordem cronológica. Inverter
        no banco e reinverter em Python é mais barato e mais óbvio que uma
        subquery, e o `limit` mantém o custo constante numa sessão longa.

        O eager load dos trechos vem junto por obrigação, não por escolha: sem
        ele o `turn_from_row` estoura com `MissingGreenlet` ao tocar a coleção
        (`lazy="raise_on_sql"` no modelo). O histórico não usa os trechos — mas
        o mapeador é um só, e ter um mapeador "parcial" para economizar um
        SELECT seria trocar um custo medido por um modo de falha novo.
        """
        stmt = (
            select(TurnRow)
            .where(
                TurnRow.session_id == session_id,
                TurnRow.status == TurnStatus.COMPLETED,
            )
            .order_by(TurnRow.created_at.desc())
            .limit(limit)
            .options(self._COM_TRECHOS)
        )
        linhas = (await self._session.scalars(stmt)).all()
        return [mappers.turn_from_row(linha) for linha in reversed(linhas)]
