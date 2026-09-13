""" "Descartar" o caso de uso: idempotência, posse e o motivo da recusa (CARD-032).

A corrida de verdade contra a conclusão do worker (RNF6) mora em
`tests/adapters/test_persistence.py`, contra Postgres real — aqui o que se
verifica é a REGRA: quem pode descartar o quê, e o que volta em cada caso.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fakes_pipeline import FakeSessionRepository, FakeTurnRepository, FakeUnitOfWork
from voicecoach.application.result import Err, Ok
from voicecoach.application.use_cases.discard_turn import (
    DiscardTurn,
    DiscardTurnHandler,
    TurnAlreadyCompleted,
    TurnNotFound,
)
from voicecoach.domain.session import Session
from voicecoach.domain.turn import Turn

ALUNO = UUID("00000000-0000-0000-0000-000000000001")
OUTRO_ALUNO = UUID("00000000-0000-0000-0000-000000000002")
AGORA = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)


def sessao_do(student_id: UUID) -> Session:
    return Session(id=uuid4(), student_id=student_id, started_at=AGORA)


def turn_em(sessao: Session, *, status_completo: bool = False) -> Turn:
    turn = sessao.start_turn(
        turn_id=uuid4(),
        input_audio_ref="dev/entrada.m4a",
        audio_duration=timedelta(seconds=4),
        now=AGORA,
    )
    if status_completo:
        turn.start_processing(AGORA)
        turn.attach_transcript("I go to the beach", AGORA)
        turn.attach_reply("Which beach?", AGORA)
        turn.attach_reply_audio("dev/resposta.mp3", AGORA)
        turn.complete(AGORA)
    return turn


def montar(
    *, sessao: Session, turn: Turn
) -> tuple[DiscardTurnHandler, FakeTurnRepository, FakeUnitOfWork]:
    turns = FakeTurnRepository(turn)
    uow = FakeUnitOfWork()
    handler = DiscardTurnHandler(
        turns=turns,
        sessions=FakeSessionRepository(sessao),
        unit_of_work=uow,
        clock=lambda: AGORA,
    )
    return handler, turns, uow


async def test_descarta_um_turn_processando() -> None:
    sessao = sessao_do(ALUNO)
    turn = turn_em(sessao)
    handler, turns, uow = montar(sessao=sessao, turn=turn)

    resultado = await handler.handle(DiscardTurn(turn_id=turn.id, student_id=ALUNO))

    assert isinstance(resultado, Ok)
    assert turns.turns[turn.id].discarded_at == AGORA
    assert uow.commits == 1


async def test_turn_completo_e_recusado_e_nao_comita() -> None:
    sessao = sessao_do(ALUNO)
    turn = turn_em(sessao, status_completo=True)
    handler, _turns, uow = montar(sessao=sessao, turn=turn)

    resultado = await handler.handle(DiscardTurn(turn_id=turn.id, student_id=ALUNO))

    assert isinstance(resultado, Err)
    assert isinstance(resultado.error, TurnAlreadyCompleted)
    assert uow.commits == 0


async def test_turn_inexistente_e_err_nao_excecao() -> None:
    sessao = sessao_do(ALUNO)
    turn = turn_em(sessao)
    handler, _turns, _uow = montar(sessao=sessao, turn=turn)

    resultado = await handler.handle(DiscardTurn(turn_id=uuid4(), student_id=ALUNO))

    assert isinstance(resultado, Err)
    assert isinstance(resultado.error, TurnNotFound)


async def test_turn_de_outro_aluno_e_mascarado_como_not_found() -> None:
    """RNF2: um 404 idêntico ao de id inexistente — sem oráculo de existência."""
    sessao = sessao_do(ALUNO)
    turn = turn_em(sessao)
    handler, turns, uow = montar(sessao=sessao, turn=turn)

    resultado = await handler.handle(
        DiscardTurn(turn_id=turn.id, student_id=OUTRO_ALUNO)
    )

    assert isinstance(resultado, Err)
    assert isinstance(resultado.error, TurnNotFound)
    assert turns.turns[turn.id].discarded_at is None
    assert uow.commits == 0


async def test_descartar_duas_vezes_e_idempotente() -> None:
    sessao = sessao_do(ALUNO)
    turn = turn_em(sessao)
    handler, turns, _uow = montar(sessao=sessao, turn=turn)
    comando = DiscardTurn(turn_id=turn.id, student_id=ALUNO)

    primeiro = await handler.handle(comando)
    segundo = await handler.handle(comando)

    assert isinstance(primeiro, Ok)
    assert isinstance(segundo, Ok)
    assert turns.turns[turn.id].discarded_at == AGORA
