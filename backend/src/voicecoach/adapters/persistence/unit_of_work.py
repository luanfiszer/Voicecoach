"""Unidade de trabalho sobre a ``AsyncSession`` (ADR-0004, ADR-0036).

**Por que existe, se a própria ``AsyncSession`` já satisfaz a porta.** Ela
satisfaz — tem ``commit`` async e nada mais é exigido —, e é exatamente assim
que o worker a usa (``worker/main.py`` passa a sessão direto). O que o worker
não tem é a restrição de unicidade da ``Idempotency-Key``.

Na API tem. E o erro que o Postgres devolve nessa colisão é um
``sqlalchemy.exc.IntegrityError`` — um tipo que ``application`` **não pode
importar** (ADR-0012). Sem tradução, o caso de uso teria duas saídas ruins:
capturar `Exception` genérica (proibido pelo ADR-0015) ou deixar um duplo
toque no botão virar 500.

Este wrapper é a tradução, e só ela. Ele não abre nem fecha a sessão: quem faz
isso é a dependência do FastAPI, por request.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.exc import IntegrityError

from voicecoach.application.ports.repositories import ConflictingWriteError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class SqlAlchemyUnitOfWork:
    """Implementa ``application.ports.repositories.UnitOfWork``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def commit(self) -> None:
        """Confirma, traduzindo violação de unicidade em erro de porta.

        O ``rollback`` antes de levantar não é zelo: depois de um
        ``IntegrityError`` a sessão fica em estado inválido, e **qualquer**
        consulta seguinte falha com ``PendingRollbackError``. Como o caso de uso
        vai justamente reconsultar (para descobrir o ``turn_id`` de quem chegou
        primeiro), sem isto a tradução resolveria um problema e criaria outro.
        """
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            message = f"escrita recusada por restrição de unicidade: {exc.orig}"
            raise ConflictingWriteError(message) from exc
