"""``EndSessionHandler``: idempotência e o resumo (CARD-031).

A atomicidade de verdade (dois `POST /end` concorrentes) mora em
`tests/adapters/test_end_session_postgres.py`, contra Postgres real — aqui o
que se verifica é a REGRA de negócio: o que devolve, em que ordem.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fakes_pipeline import FakeSessionRepository, FakeUnitOfWork, RelogioFalso
from voicecoach.application.result import Err, Ok
from voicecoach.application.use_cases.end_session import (
    EndSession,
    EndSessionHandler,
    SessionNotFound,
)
from voicecoach.domain.session import Session

ALUNO = UUID("00000000-0000-0000-0000-000000000001")
INICIO = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)


def sessao_ativa() -> Session:
    return Session(id=uuid4(), student_id=ALUNO, started_at=INICIO)


def montar(
    session: Session, *, clock: RelogioFalso | None = None
) -> tuple[EndSessionHandler, FakeSessionRepository, FakeUnitOfWork]:
    sessions = FakeSessionRepository(session)
    uow = FakeUnitOfWork()
    handler = EndSessionHandler(
        sessions=sessions,
        unit_of_work=uow,
        clock=clock or RelogioFalso(inicio=INICIO + timedelta(minutes=5)),
    )
    return handler, sessions, uow


async def test_sessao_inexistente_e_err_e_nao_excecao() -> None:
    handler, _sessions, uow = montar(sessao_ativa())

    resultado = await handler.handle(EndSession(session_id=uuid4()))

    assert isinstance(resultado, Err)
    assert isinstance(resultado.error, SessionNotFound)
    assert uow.commits == 0


async def test_encerra_e_devolve_o_resumo_vazio_sem_nenhum_turn() -> None:
    """RF5: sessão sem turn nenhum tem resumo pronto, não erro."""
    session = sessao_ativa()
    handler, sessions, uow = montar(session)

    resultado = await handler.handle(EndSession(session_id=session.id))

    assert isinstance(resultado, Ok)
    resumo = resultado.value
    assert resumo.turns == 0
    assert resumo.spoken == timedelta(0)
    assert resumo.corrections_by_type == {}
    assert sessions.sessions[session.id].ended_at is not None
    assert uow.commits == 1


async def test_chamar_de_novo_numa_sessao_ja_encerrada_e_idempotente() -> None:
    """RF2: a segunda chamada não é erro — é a mesma pergunta, respondida de novo."""
    session = sessao_ativa()
    clock = RelogioFalso(inicio=INICIO + timedelta(minutes=5))
    handler, sessions, _uow = montar(session, clock=clock)

    primeiro = await handler.handle(EndSession(session_id=session.id))
    ended_at_primeiro = sessions.sessions[session.id].ended_at
    segundo = await handler.handle(EndSession(session_id=session.id))

    assert isinstance(primeiro, Ok)
    assert isinstance(segundo, Ok)
    assert primeiro.value == segundo.value
    # O relógio andou entre as duas chamadas, mas `ended_at` não se move.
    assert sessions.sessions[session.id].ended_at == ended_at_primeiro
