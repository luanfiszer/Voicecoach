"""``GetTurnHandler``: só o dono lê o turn (RNF2, CARD-062)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fakes_pipeline import FakeSessionRepository, FakeTurnRepository
from voicecoach.application.result import Err, Ok
from voicecoach.application.use_cases.get_turn import (
    GetTurn,
    GetTurnHandler,
    TurnNotFound,
)
from voicecoach.domain.session import Session
from voicecoach.domain.turn import Turn

ALUNO = UUID("00000000-0000-0000-0000-000000000001")
AGORA = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def montar() -> tuple[GetTurnHandler, Turn]:
    session = Session(id=uuid4(), student_id=ALUNO, started_at=AGORA)
    turn = session.start_turn(
        turn_id=uuid4(),
        input_audio_ref="entrada",
        audio_duration=timedelta(seconds=2),
        now=AGORA,
        idempotency_key="chave-get-turn",
    )
    handler = GetTurnHandler(
        turns=FakeTurnRepository(turn), sessions=FakeSessionRepository(session)
    )
    return handler, turn


async def test_o_dono_le_o_turn() -> None:
    handler, turn = montar()

    resultado = await handler.handle(GetTurn(turn_id=turn.id, student_id=ALUNO))

    assert resultado == Ok(turn)


async def test_outro_aluno_recebe_o_mesmo_err_do_inexistente() -> None:
    """O defeito que originou o CARD-062: qualquer um com o UUID lia o turn."""
    handler, turn = montar()

    alheio = await handler.handle(GetTurn(turn_id=turn.id, student_id=uuid4()))
    inexistente_id = uuid4()
    inexistente = await handler.handle(
        GetTurn(turn_id=inexistente_id, student_id=ALUNO)
    )

    assert alheio == Err(TurnNotFound(turn.id))
    assert inexistente == Err(TurnNotFound(inexistente_id))
