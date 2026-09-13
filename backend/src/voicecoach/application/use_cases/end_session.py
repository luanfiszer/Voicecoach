"""Encerra uma sessão e devolve o resumo pós-sessão (CARD-031, artboard 09).

**A mutação não é "ler, mudar em memória, gravar".** É um `UPDATE` condicional
atômico (`SessionRepository.try_end`) — a única forma de dois `POST /end`
concorrentes, em duas conexões de banco diferentes, nunca produzirem dois
`ended_at` diferentes (RNF4). Ver o docstring de `Session.end()` para o porquê
completo: o domínio nomeia a invariante, o banco a impõe entre escritores
concorrentes, o mesmo princípio do índice único de `idempotency_key` em
``StartTurn``.

**Por que isto é sempre `Ok`.** Encerrar é idempotente do ponto de vista do
cliente (RF2) — a única forma de "errar" é a sessão não existir, e isso é
`SessionNotFound`. Chamar `/end` numa sessão já encerrada não é uma segunda
tentativa de uma operação que pode falhar: é a MESMA pergunta ("qual o resumo
desta sessão, encerrada agora ou antes?"), sempre respondida.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from voicecoach.application.result import Err, Ok, Result

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime
    from uuid import UUID

    from voicecoach.application.ports.repositories import SessionRepository, UnitOfWork
    from voicecoach.domain.session import SessionSummary


@dataclass(frozen=True, slots=True)
class EndSession:
    """O comando: só o id. Quem encerra é sempre o dono da sessão (Fase 3, auth)."""

    session_id: UUID


@dataclass(frozen=True, slots=True)
class SessionNotFound:
    """A sessão referida não existe — o mesmo desfecho do `StartTurn`."""

    session_id: UUID


class EndSessionHandler:
    """Encerra (ou confirma já-encerrada) e monta o resumo."""

    def __init__(
        self,
        *,
        sessions: SessionRepository,
        unit_of_work: UnitOfWork,
        clock: Callable[[], datetime],
    ) -> None:
        self._sessions = sessions
        self._uow = unit_of_work
        self._clock = clock

    async def handle(
        self, command: EndSession
    ) -> Result[SessionSummary, SessionNotFound]:
        session = await self._sessions.get(command.session_id)
        if session is None:
            return Err(SessionNotFound(command.session_id))

        # `try_end` é quem decide de verdade, atomicamente. Não há exceção a
        # capturar aqui: idempotência é o comportamento normal do método, não
        # um caminho de erro traduzido.
        await self._sessions.try_end(session.id, self._clock())
        await self._uow.commit()

        resumo = await self._sessions.summary_for(session.id)
        return Ok(resumo)
