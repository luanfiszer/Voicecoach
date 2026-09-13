""" "Descartar": a ação do aluno sobre o turn que travou (CARD-032, artboard 16).

**Por que isto é sempre `Ok` ou um `Err` de dois motivos, nunca exceção.**
`TurnAlreadyCompleted` é o desfecho **esperado** do ADR-0039: o aluno pode
clicar "Descartar" bem no instante em que a resposta chega, e isso não é bug
de ninguém — é uma corrida legítima entre o clique e o worker. `TurnNotFound`
cobre tanto o id inexistente quanto o turn de outro aluno (RNF2): as duas
situações recebem o MESMO `Err`, de propósito — um 404 idêntico não dá a quem
tenta descartar o turn alheio nenhuma pista sobre se o id existe.

**Nada aqui apaga nada** (RF1/RF4). O único efeito é
``TurnRepository.try_discard`` marcar ``discarded_at`` — ver o docstring dele
para a garantia de atomicidade contra a conclusão concorrente do worker
(RNF6).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from voicecoach.application.result import Err, Ok, Result

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime
    from uuid import UUID

    from voicecoach.application.ports.repositories import (
        SessionRepository,
        TurnRepository,
        UnitOfWork,
    )


@dataclass(frozen=True, slots=True)
class DiscardTurn:
    """O comando: qual turn, pedido por qual aluno (RNF2 — checado no handle)."""

    turn_id: UUID
    student_id: UUID


@dataclass(frozen=True, slots=True)
class TurnNotFound:
    """O turn não existe, OU existe mas não é do aluno da requisição (RNF2).

    Um só tipo para os dois casos — a distinção não pode vazar para fora do
    caso de uso, ou o 404 vira um oráculo de "este id existe" para quem não é
    dono.
    """

    turn_id: UUID


@dataclass(frozen=True, slots=True)
class TurnAlreadyCompleted:
    """O turn já entregou a resposta — descartar isto é outra conversa (RF2)."""

    turn_id: UUID


type DiscardTurnRejection = TurnNotFound | TurnAlreadyCompleted


class DiscardTurnHandler:
    def __init__(
        self,
        *,
        turns: TurnRepository,
        sessions: SessionRepository,
        unit_of_work: UnitOfWork,
        clock: Callable[[], datetime],
    ) -> None:
        self._turns = turns
        self._sessions = sessions
        self._uow = unit_of_work
        self._clock = clock

    async def handle(self, command: DiscardTurn) -> Result[None, DiscardTurnRejection]:
        turn = await self._turns.get(command.turn_id)
        if turn is None:
            return Err(TurnNotFound(command.turn_id))

        session = await self._sessions.get(turn.session_id)
        if session is None or session.student_id != command.student_id:
            # RNF2: mascarado como TurnNotFound — ver o docstring da classe.
            return Err(TurnNotFound(command.turn_id))

        discarded_at = await self._turns.try_discard(turn.id, self._clock())
        if discarded_at is None:
            return Err(TurnAlreadyCompleted(command.turn_id))

        await self._uow.commit()
        return Ok(None)
