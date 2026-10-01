"""Ler um turn — só o dono lê (RNF2, CARD-062).

Até o CARD-062, ``GET /v1/turns/{id}`` e o SSE liam o turn direto do
repositório, **sem autenticação nem dono**: quem tivesse o UUID lia a
transcrição, a resposta e as URLs assinadas do áudio de outro aluno. A regra
de dono mora aqui, e não na rota, pela mesma razão do ``DiscardTurn``: é
regra de negócio, testável com fakes, e as duas rotas (polling e SSE) a
compartilham em vez de cada uma reescrever o ``if``.

Inexistente e alheio são o MESMO ``Err`` — um 404 idêntico não diz a quem
não é dono se o id existe.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from voicecoach.application.result import Err, Ok, Result

if TYPE_CHECKING:
    from uuid import UUID

    from voicecoach.application.ports.repositories import (
        SessionRepository,
        TurnRepository,
    )
    from voicecoach.domain.turn import Turn


@dataclass(frozen=True, slots=True)
class GetTurn:
    """A consulta: qual turn, pedido por qual aluno."""

    turn_id: UUID
    student_id: UUID


@dataclass(frozen=True, slots=True)
class TurnNotFound:
    """O turn não existe, OU existe mas não é do aluno da requisição (RNF2)."""

    turn_id: UUID


class GetTurnHandler:
    def __init__(self, *, turns: TurnRepository, sessions: SessionRepository) -> None:
        self._turns = turns
        self._sessions = sessions

    async def handle(self, query: GetTurn) -> Result[Turn, TurnNotFound]:
        turn = await self._turns.get(query.turn_id)
        if turn is None:
            return Err(TurnNotFound(query.turn_id))

        session = await self._sessions.get(turn.session_id)
        if session is None or session.student_id != query.student_id:
            return Err(TurnNotFound(query.turn_id))
        return Ok(turn)
