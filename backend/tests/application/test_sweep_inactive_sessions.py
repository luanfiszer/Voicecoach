"""A varredura de sessões inativas (CARD-034), com relógio controlado.

Nenhum `sleep`: o prazo é testado movendo o relógio, que é o que o RNF4 exige —
e é a mesma disciplina do CARD-025.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fakes_pipeline import FakeSessionRepository, FakeTurnRepository, FakeUnitOfWork
from voicecoach.application.use_cases.sweep_inactive_sessions import (
    SweepInactiveSessions,
    SweepInactiveSessionsHandler,
)
from voicecoach.domain.session import Session

ALUNO = UUID("00000000-0000-0000-0000-000000000001")
AGORA = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)
PRAZO = timedelta(minutes=30)


def sessao(*, aberta_em: datetime) -> Session:
    return Session(id=uuid4(), student_id=ALUNO, started_at=aberta_em)


def montar(
    *sessoes: Session,
    turns: FakeTurnRepository | None = None,
    batch_limit: int = 50,
) -> tuple[SweepInactiveSessionsHandler, FakeSessionRepository, FakeUnitOfWork]:
    sessions = FakeSessionRepository(*sessoes, turns=turns or FakeTurnRepository())
    uow = FakeUnitOfWork()
    handler = SweepInactiveSessionsHandler(
        sessions=sessions,
        unit_of_work=uow,
        clock=lambda: AGORA,
        inactive_after=PRAZO,
        batch_limit=batch_limit,
    )
    return handler, sessions, uow


def com_turn(
    sessao_alvo: Session,
    *,
    quando: datetime,
    turns: FakeTurnRepository | None = None,
    processando: bool = False,
) -> FakeTurnRepository:
    turns = turns or FakeTurnRepository()
    turn = sessao_alvo.start_turn(
        turn_id=uuid4(),
        input_audio_ref="dev/entrada.m4a",
        audio_duration=timedelta(seconds=4),
        now=quando,
    )
    if processando:
        turn.start_processing(quando)
    else:
        turn.start_processing(quando)
        turn.attach_transcript("hi", quando)
        turn.attach_reply("Nice.", quando)
        turn.attach_reply_audio("dev/resposta.mp3", quando)
        turn.complete(quando)
    turns.turns[turn.id] = turn
    return turns


async def test_sessao_parada_alem_do_prazo_e_encerrada() -> None:
    """Critério de aceite: último turn antigo ⇒ `ended_at` preenchido."""
    alvo = sessao(aberta_em=AGORA - timedelta(hours=3))
    handler, sessions, uow = montar(
        alvo, turns=com_turn(alvo, quando=AGORA - timedelta(hours=2))
    )

    relatorio = await handler.handle(SweepInactiveSessions())

    assert relatorio.encerradas == 1
    assert sessions.sessions[alvo.id].ended_at == AGORA
    assert uow.commits == 1


async def test_sessao_dentro_do_prazo_nao_e_tocada() -> None:
    alvo = sessao(aberta_em=AGORA - timedelta(hours=1))
    handler, sessions, uow = montar(
        alvo, turns=com_turn(alvo, quando=AGORA - timedelta(minutes=5))
    )

    relatorio = await handler.handle(SweepInactiveSessions())

    assert relatorio.examinadas == 0
    assert sessions.sessions[alvo.id].ended_at is None
    assert uow.commits == 0


async def test_sessao_antiga_com_turn_processando_nao_e_encerrada() -> None:
    """RF3: o aluno pode estar esperando uma resposta travada — é do CARD-025."""
    alvo = sessao(aberta_em=AGORA - timedelta(hours=5))
    handler, sessions, _uow = montar(
        alvo,
        turns=com_turn(alvo, quando=AGORA - timedelta(hours=4), processando=True),
    )

    relatorio = await handler.handle(SweepInactiveSessions())

    assert relatorio.examinadas == 0
    assert sessions.sessions[alvo.id].ended_at is None


async def test_sessao_sem_turn_nenhum_conta_do_started_at() -> None:
    """RF2: o aluno abriu e nunca falou — ela também fecha."""
    alvo = sessao(aberta_em=AGORA - timedelta(hours=2))
    handler, sessions, _uow = montar(alvo)

    relatorio = await handler.handle(SweepInactiveSessions())

    assert relatorio.encerradas == 1
    assert sessions.sessions[alvo.id].ended_at == AGORA


async def test_sessao_ja_encerrada_nunca_reaparece_como_candidata() -> None:
    """RNF3, do lado da consulta: quem já fechou sai do conjunto."""
    alvo = sessao(aberta_em=AGORA - timedelta(hours=3))
    alvo.ended_at = AGORA - timedelta(hours=1)
    handler, _sessions, uow = montar(alvo)

    relatorio = await handler.handle(SweepInactiveSessions())

    assert relatorio.examinadas == 0
    assert uow.commits == 0


async def test_o_lote_limita_e_a_rodada_seguinte_pega_o_resto() -> None:
    """Critério de aceite: 6 candidatas, lote de 2 ⇒ três rodadas, sem pular."""
    antigas = [sessao(aberta_em=AGORA - timedelta(hours=i + 2)) for i in range(6)]
    handler, sessions, _uow = montar(*antigas, batch_limit=2)

    encerradas = 0
    for _ in range(3):
        encerradas += (await handler.handle(SweepInactiveSessions())).encerradas

    assert encerradas == 6
    assert all(s.ended_at == AGORA for s in sessions.sessions.values())


async def test_rodar_duas_vezes_e_idempotente_e_nao_levanta() -> None:
    """RNF3: `try_end` é COALESCE — a segunda rodada não acha nada e não explode."""
    alvo = sessao(aberta_em=AGORA - timedelta(hours=3))
    handler, sessions, _uow = montar(alvo)

    primeira = await handler.handle(SweepInactiveSessions())
    segunda = await handler.handle(SweepInactiveSessions())

    assert primeira.encerradas == 1
    assert segunda.examinadas == 0
    assert sessions.sessions[alvo.id].ended_at == AGORA


async def test_sessao_apagada_entre_a_listagem_e_a_escrita_nao_derruba_o_lote() -> None:
    """Uma sessão não pode derrubar a rodada — a mesma regra do CARD-025."""
    some = sessao(aberta_em=AGORA - timedelta(hours=4))
    fica = sessao(aberta_em=AGORA - timedelta(hours=3))

    class RepositorioQuePerdeALinha(FakeSessionRepository):
        async def try_end(self, session_id: UUID, now: datetime) -> datetime:
            if session_id == some.id:
                del self.sessions[some.id]
            return await super().try_end(session_id, now)

    handler = SweepInactiveSessionsHandler(
        sessions=RepositorioQuePerdeALinha(some, fica),
        unit_of_work=FakeUnitOfWork(),
        clock=lambda: AGORA,
        inactive_after=PRAZO,
        batch_limit=50,
    )

    relatorio = await handler.handle(SweepInactiveSessions())

    assert relatorio.examinadas == 2
    assert relatorio.ignoradas == 1
    assert relatorio.encerradas == 1
