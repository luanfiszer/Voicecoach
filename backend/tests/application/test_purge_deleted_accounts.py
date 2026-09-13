"""``PurgeDeletedAccountsHandler`` — o expurgo físico (CARD-051, ADR-0069).

A ordem testada é a garantia central do card: turns antes de sessions, e o
storage antes do `Student`. O caminho triste (storage fora) é o que prova o
critério de aceite mais caro: a conta segue marcada e inacessível até o
storage responder.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fakes_pipeline import (
    FakeMediaStorage,
    FakeSessionRepository,
    FakeStudentRepository,
    FakeTurnRepository,
    FakeUnitOfWork,
)
from voicecoach.application.ports.media_storage import MediaStorageError
from voicecoach.application.use_cases.purge_deleted_accounts import (
    PurgeDeletedAccounts,
    PurgeDeletedAccountsHandler,
)
from voicecoach.domain.media_keys import input_key, student_prefix
from voicecoach.domain.session import Session
from voicecoach.domain.student import Student

AGORA = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)


def montar_conta_marcada(
    student_id: UUID, *, com_conteudo: bool = True
) -> tuple[
    PurgeDeletedAccountsHandler,
    FakeStudentRepository,
    FakeSessionRepository,
    FakeTurnRepository,
    FakeMediaStorage,
    FakeUnitOfWork,
]:
    aluno = Student(
        id=student_id, display_name="Aluno", created_at=AGORA, deleted_at=AGORA
    )
    students = FakeStudentRepository(aluno)
    sessao = Session(id=uuid4(), student_id=student_id, started_at=AGORA)
    sessions = FakeSessionRepository(sessao)
    turns = FakeTurnRepository(sessions=sessions)
    storage = FakeMediaStorage()

    if com_conteudo:
        turn = sessao.start_turn(
            turn_id=uuid4(),
            input_audio_ref="dev/entrada.m4a",
            audio_duration=timedelta(seconds=4),
            now=AGORA,
        )
        turns.turns[turn.id] = turn
        chave = input_key(student_id, sessao.id, turn.id, "m4a")
        storage.objetos[chave] = (b"audio", "audio/m4a")

    uow = FakeUnitOfWork()
    handler = PurgeDeletedAccountsHandler(
        students=students,
        sessions=sessions,
        turns=turns,
        storage=storage,
        unit_of_work=uow,
        clock=lambda: AGORA,
        batch_limit=50,
    )
    return handler, students, sessions, turns, storage, uow


async def test_expurga_conteudo_storage_e_a_propria_conta() -> None:
    student_id = uuid4()
    handler, students, sessions, turns, storage, uow = montar_conta_marcada(student_id)

    relatorio = await handler.handle(PurgeDeletedAccounts())

    assert relatorio.examinadas == 1
    assert relatorio.expurgadas == 1
    assert relatorio.falharam_no_storage == 0
    assert await students.get(student_id) is None
    assert sessions.sessions == {}
    assert turns.turns == {}
    assert storage.objetos == {}
    assert uow.commits == 2  # um após turns+sessions, outro após o storage


async def test_e_idempotente_rodar_duas_vezes_e_sucesso() -> None:
    student_id = uuid4()
    handler, students, _sessions, _turns, _storage, _uow = montar_conta_marcada(
        student_id
    )

    primeiro = await handler.handle(PurgeDeletedAccounts())
    segundo = await handler.handle(PurgeDeletedAccounts())

    assert primeiro.expurgadas == 1
    # Na segunda rodada a conta já não existe mais em `list_pending_purge`.
    assert segundo.examinadas == 0
    assert segundo.expurgadas == 0
    assert await students.get(student_id) is None


async def test_storage_fora_deixa_a_conta_marcada_e_inacessivel() -> None:
    """O critério de aceite mais caro: falha no storage não apaga o Student,
    e a próxima rodada (aqui, uma segunda chamada) tenta de novo.
    """
    student_id = uuid4()
    handler, students, sessions, turns, storage, _uow = montar_conta_marcada(student_id)
    storage._falhar_em = MediaStorageError("MinIO fora do ar")

    relatorio = await handler.handle(PurgeDeletedAccounts())

    assert relatorio.expurgadas == 0
    assert relatorio.falharam_no_storage == 1
    aluno = await students.get(student_id)
    assert aluno is not None
    assert not aluno.is_active
    # Turns/sessions já foram apagados — idempotente na próxima rodada.
    assert sessions.sessions == {}
    assert turns.turns == {}

    storage._falhar_em = None
    segunda = await handler.handle(PurgeDeletedAccounts())

    assert segunda.expurgadas == 1
    assert await students.get(student_id) is None


async def test_conta_sem_conteudo_expurga_so_a_propria_linha() -> None:
    """O S3 vazio: `delete_prefix` de um prefixo sem objetos é sucesso, zero
    (o mesmo idioma do adapter real).
    """
    student_id = uuid4()
    handler, students, sessions, turns, storage, uow = montar_conta_marcada(
        student_id, com_conteudo=False
    )

    relatorio = await handler.handle(PurgeDeletedAccounts())

    assert relatorio.expurgadas == 1
    assert await students.get(student_id) is None
    assert sessions.sessions == {}
    assert turns.turns == {}
    assert storage.objetos == {}
    assert uow.commits == 2


async def test_lote_respeita_o_batch_limit() -> None:
    """Duas contas marcadas, sem conteúdo, lote de 1 — só uma expurga por
    rodada."""
    primeira = Student(id=uuid4(), display_name="A", created_at=AGORA, deleted_at=AGORA)
    segunda = Student(
        id=uuid4(),
        display_name="B",
        created_at=AGORA,
        deleted_at=AGORA + timedelta(seconds=1),
    )
    students = FakeStudentRepository(primeira, segunda)
    handler = PurgeDeletedAccountsHandler(
        students=students,
        sessions=FakeSessionRepository(),
        turns=FakeTurnRepository(),
        storage=FakeMediaStorage(),
        unit_of_work=FakeUnitOfWork(),
        clock=lambda: AGORA,
        batch_limit=1,
    )

    relatorio = await handler.handle(PurgeDeletedAccounts())

    assert relatorio.examinadas == 1
    assert relatorio.expurgadas == 1
    # A mais antiga (`primeira`) é quem sai — `list_pending_purge` ordena por
    # `deleted_at`, o mesmo critério do adapter real.
    assert await students.get(primeira.id) is None
    assert await students.get(segunda.id) is not None


def test_student_prefix_e_o_alvo_do_delete_prefix() -> None:
    """Não é o comportamento do handler — é a garantia de que ele usa a
    MESMA função de chave que o resto do produto, não uma string à mão.
    """
    student_id = uuid4()
    assert student_prefix(student_id) == f"{student_id}/"
