"""Ciclo de vida da Session e a invariante que protege o Turn."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from voicecoach.domain.errors import InvalidStateTransitionError
from voicecoach.domain.session import Session
from voicecoach.domain.turn import TurnStatus

STARTED = datetime(2026, 8, 18, 21, 0, tzinfo=UTC)
LATER = datetime(2026, 8, 18, 23, 0, tzinfo=UTC)


def make_session() -> Session:
    return Session(id=uuid4(), student_id=uuid4(), started_at=STARTED)


def test_sessao_nasce_em_andamento() -> None:
    assert make_session().is_active


def test_start_turn_liga_o_turn_a_sessao() -> None:
    session = make_session()
    turn_id = uuid4()

    turn = session.start_turn(
        turn_id=turn_id,
        input_audio_ref="dev/entrada.m4a",
        audio_duration=timedelta(seconds=14),
        now=STARTED,
    )

    assert turn.id == turn_id
    assert turn.session_id == session.id
    assert turn.status is TurnStatus.QUEUED


def test_sessao_encerrada_recusa_turno_novo() -> None:
    """O áudio guardado offline pode chegar depois do 'Encerrar'."""
    session = make_session()
    session.end(LATER)

    with pytest.raises(InvalidStateTransitionError) as erro:
        session.start_turn(
            turn_id=uuid4(),
            input_audio_ref="dev/gravado-as-21h.m4a",
            audio_duration=timedelta(seconds=14),
            now=LATER,
        )

    assert erro.value.entity == "Session"
    assert erro.value.action == "start_turn"


def test_encerrar_marca_o_fim() -> None:
    session = make_session()
    session.end(LATER)

    assert not session.is_active
    assert session.ended_at == LATER


def test_encerrar_duas_vezes_e_recusado() -> None:
    session = make_session()
    session.end(LATER)

    with pytest.raises(InvalidStateTransitionError):
        session.end(LATER)


def test_nao_encerra_antes_de_comecar() -> None:
    session = make_session()

    with pytest.raises(ValueError, match="antes do início"):
        session.end(STARTED - timedelta(minutes=1))
