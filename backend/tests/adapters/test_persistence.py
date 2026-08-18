"""Adapters de persistência contra um Postgres de verdade (ADR-0018).

Por que container e não SQLite: o que pode dar errado aqui é justamente o que
só existe no Postgres — `TIMESTAMPTZ`, enum nativo, `INTERVAL` — e as próprias
migrations. Um dublê passaria verde escondendo os quatro.

O esquema é criado rodando `alembic upgrade head`, não `metadata.create_all()`:
assim o teste exercita o mesmo caminho que produção, e migration quebrada
reprova a suíte.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from testcontainers.community.postgres import PostgresContainer

from voicecoach.adapters.persistence.engine import (
    create_engine,
    create_session_factory,
)
from voicecoach.adapters.persistence.repositories import (
    RowNotFoundError,
    SqlAlchemySessionRepository,
    SqlAlchemyStudentRepository,
    SqlAlchemyTurnRepository,
)
from voicecoach.adapters.persistence.seed import (
    DEV_STUDENT_DISPLAY_NAME,
    DEV_STUDENT_ID,
)
from voicecoach.application.ports.repositories import (
    SessionRepository,
    StudentRepository,
    TurnRepository,
)
from voicecoach.domain.session import Session
from voicecoach.domain.student import Student
from voicecoach.domain.turn import TurnStatus

BACKEND_ROOT = Path(__file__).resolve().parents[2]
# A mesma imagem do docker-compose.yml, com a tag fixada (ADR-0010/0018).
POSTGRES_IMAGE = "postgres:16.15-alpine"

NOW = datetime(2026, 8, 18, 21, 0, tzinfo=UTC)


def _run_migrations(database_url: str) -> None:
    """Aplica `alembic upgrade head` no banco do container.

    Fixture **síncrona** de propósito: o `env.py` do Alembic chama
    `asyncio.run()`, que explode se já houver um event loop rodando — e haveria,
    se isto estivesse dentro de um teste async.
    """
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """Um Postgres descartável por execução da suíte."""
    with PostgresContainer(POSTGRES_IMAGE, driver="asyncpg") as container:
        url = container.get_connection_url()
        _run_migrations(url)
        yield url


@pytest.fixture
async def db_session(database_url: str) -> AsyncIterator[AsyncSession]:
    engine = create_engine(database_url)
    factory = create_session_factory(engine)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def sessao_persistida(db_session: AsyncSession) -> Session:
    """Uma Session já gravada, do Student de desenvolvimento."""
    session = Session(id=uuid4(), student_id=DEV_STUDENT_ID, started_at=NOW)
    repository: SessionRepository = SqlAlchemySessionRepository(db_session)
    await repository.add(session)
    await db_session.commit()
    return session


async def test_upgrade_head_cria_o_student_dev(db_session: AsyncSession) -> None:
    """Critério de aceite: banco vazio + `alembic upgrade head` ⇒ Student dev existe."""
    # A anotação com o tipo da PORTA é o que faz o mypy verificar que o adapter
    # satisfaz o Protocol — estruturalmente, sem herança nem registro.
    repository: StudentRepository = SqlAlchemyStudentRepository(db_session)

    student = await repository.get(DEV_STUDENT_ID)

    assert student is not None
    assert student.display_name == DEV_STUDENT_DISPLAY_NAME


def test_constante_do_codigo_bate_com_a_da_migration() -> None:
    """A migration não importa o código; um teste impede que os dois divirjam."""
    migration = (
        BACKEND_ROOT
        / "alembic/versions/d790e74af8f6_seed_do_student_de_desenvolvimento.py"
    ).read_text(encoding="utf-8")

    assert str(DEV_STUDENT_ID) in migration
    assert DEV_STUDENT_DISPLAY_NAME in migration


async def test_roundtrip_do_turn_preserva_campos_e_estado(
    db_session: AsyncSession, sessao_persistida: Session
) -> None:
    """Critério de aceite: salvar e recarregar não perde nada."""
    repository: TurnRepository = SqlAlchemyTurnRepository(db_session)
    turn = sessao_persistida.start_turn(
        turn_id=uuid4(),
        input_audio_ref="dev/entrada.m4a",
        audio_duration=timedelta(seconds=14, milliseconds=500),
        now=NOW,
    )
    turn.start_processing(NOW)
    turn.attach_transcript("I go to the beach", NOW)

    await repository.add(turn)
    await db_session.commit()
    db_session.expunge_all()  # força ler do banco, não do cache de identidade

    recarregado = await repository.get(turn.id)

    # Igualdade por valor do @dataclass: compara todos os campos de uma vez.
    assert recarregado == turn
    assert recarregado is not None
    assert recarregado.status is TurnStatus.PROCESSING
    assert recarregado.audio_duration == timedelta(seconds=14, milliseconds=500)
    assert recarregado.created_at.tzinfo is not None  # TIMESTAMPTZ, não ingênuo


async def test_update_persiste_a_transicao_do_pipeline(
    db_session: AsyncSession, sessao_persistida: Session
) -> None:
    repository: TurnRepository = SqlAlchemyTurnRepository(db_session)
    turn = sessao_persistida.start_turn(
        turn_id=uuid4(),
        input_audio_ref="dev/entrada.m4a",
        audio_duration=timedelta(seconds=14),
        now=NOW,
    )
    await repository.add(turn)
    await db_session.commit()

    turn.start_processing(NOW)
    turn.attach_transcript("I go to the beach", NOW)
    turn.attach_reply("Which beach did you go to?", NOW)
    turn.attach_reply_audio("dev/resposta.mp3", NOW)
    turn.complete(NOW)
    await repository.update(turn)
    await db_session.commit()
    db_session.expunge_all()

    recarregado = await repository.get(turn.id)

    assert recarregado is not None
    assert recarregado.status is TurnStatus.COMPLETED
    assert recarregado.reply_audio_ref == "dev/resposta.mp3"
    assert recarregado.completed_at == NOW


async def test_status_vai_para_o_banco_como_valor_e_nao_como_nome(
    db_session: AsyncSession, sessao_persistida: Session
) -> None:
    """`values_callable` nos modelos: a coluna guarda 'queued', não 'QUEUED'."""
    repository: TurnRepository = SqlAlchemyTurnRepository(db_session)
    turn = sessao_persistida.start_turn(
        turn_id=uuid4(),
        input_audio_ref="dev/entrada.m4a",
        audio_duration=timedelta(seconds=14),
        now=NOW,
    )
    await repository.add(turn)
    await db_session.commit()

    resultado = await db_session.execute(
        text("SELECT status::text FROM turns WHERE id = :id"), {"id": turn.id}
    )

    assert resultado.scalar_one() == "queued"


async def test_get_de_id_inexistente_devolve_none(db_session: AsyncSession) -> None:
    repository: TurnRepository = SqlAlchemyTurnRepository(db_session)

    assert await repository.get(uuid4()) is None


async def test_update_de_turn_inexistente_e_erro_de_adapter(
    db_session: AsyncSession, sessao_persistida: Session
) -> None:
    """Não é violação de regra de negócio (ADR-0017) — é bug de orquestração."""
    repository: TurnRepository = SqlAlchemyTurnRepository(db_session)
    nunca_gravado = sessao_persistida.start_turn(
        turn_id=uuid4(),
        input_audio_ref="dev/entrada.m4a",
        audio_duration=timedelta(seconds=14),
        now=NOW,
    )

    with pytest.raises(RowNotFoundError):
        await repository.update(nunca_gravado)


async def test_encerrar_sessao_persiste(
    db_session: AsyncSession, sessao_persistida: Session
) -> None:
    repository: SessionRepository = SqlAlchemySessionRepository(db_session)
    sessao_persistida.end(NOW + timedelta(minutes=8))

    await repository.update(sessao_persistida)
    await db_session.commit()
    db_session.expunge_all()

    recarregada = await repository.get(sessao_persistida.id)

    assert recarregada is not None
    assert not recarregada.is_active


async def test_student_novo_faz_roundtrip(db_session: AsyncSession) -> None:
    repository: StudentRepository = SqlAlchemyStudentRepository(db_session)
    student = Student(id=uuid4(), display_name="Ana Souza", created_at=NOW)

    await repository.add(student)
    await db_session.commit()
    db_session.expunge_all()

    assert await repository.get(student.id) == student


def test_id_do_student_dev_e_estavel() -> None:
    assert UUID("00000000-0000-0000-0000-000000000001") == DEV_STUDENT_ID
