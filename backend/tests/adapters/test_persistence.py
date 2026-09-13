"""Adapters de persistência contra um Postgres de verdade (ADR-0018).

Por que container e não SQLite: o que pode dar errado aqui é justamente o que
só existe no Postgres — `TIMESTAMPTZ`, enum nativo, `INTERVAL` — e as próprias
migrations. Um dublê passaria verde escondendo os quatro.

O esquema é criado rodando `alembic upgrade head`, não `metadata.create_all()`:
assim o teste exercita o mesmo caminho que produção, e migration quebrada
reprova a suíte.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from testcontainers.community.postgres import PostgresContainer

from voicecoach.adapters.persistence.engine import (
    create_engine,
    create_session_factory,
)
from voicecoach.adapters.persistence.mappers import StaleTurnError
from voicecoach.adapters.persistence.repositories import (
    SqlAlchemyCredentialRepository,
    SqlAlchemyEmailVerificationTokenRepository,
    SqlAlchemyPasswordResetTokenRepository,
    SqlAlchemyRefreshTokenRepository,
    SqlAlchemySessionRepository,
    SqlAlchemyStudentRepository,
    SqlAlchemyTranslationRepository,
    SqlAlchemyTurnRepository,
    SqlAlchemyUsageEventRepository,
)
from voicecoach.adapters.persistence.seed import (
    DEV_STUDENT_DISPLAY_NAME,
    DEV_STUDENT_ID,
)
from voicecoach.adapters.persistence.unit_of_work import SqlAlchemyUnitOfWork
from voicecoach.application.ports.auth_repositories import (
    CredentialRepository,
    EmailVerificationTokenRepository,
    PasswordResetTokenRepository,
    RefreshTokenRepository,
)
from voicecoach.application.ports.repositories import (
    ConflictingWriteError,
    RowNotFoundError,
    SessionRepository,
    StudentRepository,
    TranslationRepository,
    TurnRepository,
    UnitOfWork,
    UsageEventRepository,
)
from voicecoach.domain.auth import (
    Credential,
    EmailVerificationToken,
    PasswordResetToken,
    RefreshToken,
)
from voicecoach.domain.correction import Correction, CorrectionType, Severity
from voicecoach.domain.session import Session
from voicecoach.domain.student import Student
from voicecoach.domain.translation import Translation, TranslationTarget
from voicecoach.domain.turn import Turn, TurnStatus
from voicecoach.domain.usage import UsageEvent

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


async def test_list_by_session_devolve_so_os_concluidos_em_ordem_cronologica(
    db_session: AsyncSession, sessao_persistida: Session
) -> None:
    """O histórico do professor (CARD-009).

    Três turnos: dois concluídos e um que falhou. O que falhou **não** entra —
    ele não tem os dois lados do diálogo, e alimentar o professor com metade de
    uma troca ensinaria a ele um padrão de conversa que não existe.
    """
    repository: TurnRepository = SqlAlchemyTurnRepository(db_session)

    async def turno(minuto: int, *, concluido: bool) -> Turn:
        turn = sessao_persistida.start_turn(
            turn_id=uuid4(),
            input_audio_ref=f"dev/{minuto}.m4a",
            audio_duration=timedelta(seconds=10),
            now=NOW + timedelta(minutes=minuto),
        )
        await repository.add(turn)
        turn.start_processing(NOW + timedelta(minutes=minuto))
        turn.attach_transcript(f"fala {minuto}", NOW + timedelta(minutes=minuto))
        if concluido:
            turn.attach_reply(f"resposta {minuto}", NOW + timedelta(minutes=minuto))
            turn.attach_reply_audio(
                f"dev/{minuto}.mp3", NOW + timedelta(minutes=minuto)
            )
            turn.complete(NOW + timedelta(minutes=minuto))
        else:
            turn.fail("tts caiu", NOW + timedelta(minutes=minuto))
        await repository.update(turn)
        return turn

    await turno(1, concluido=True)
    await turno(2, concluido=False)
    await turno(3, concluido=True)
    await db_session.commit()
    db_session.expunge_all()

    historico = await repository.list_by_session(sessao_persistida.id, limit=10)

    assert [t.transcript for t in historico] == ["fala 1", "fala 3"]


async def test_list_by_session_corta_os_mais_velhos_e_nao_os_mais_novos(
    db_session: AsyncSession, sessao_persistida: Session
) -> None:
    """O `limit` protege o custo de tokens — e tem de cortar o lado certo.

    A query ordena decrescente para pegar os N mais recentes; o resultado volta
    cronológico porque é assim que o histórico é montado. Cortar ao contrário
    daria ao professor o começo da conversa e não o que acabou de ser dito.
    """
    repository: TurnRepository = SqlAlchemyTurnRepository(db_session)
    for minuto in (1, 2, 3):
        turn = sessao_persistida.start_turn(
            turn_id=uuid4(),
            input_audio_ref=f"dev/{minuto}.m4a",
            audio_duration=timedelta(seconds=10),
            now=NOW + timedelta(minutes=minuto),
        )
        await repository.add(turn)
        turn.start_processing(NOW + timedelta(minutes=minuto))
        turn.attach_transcript(f"fala {minuto}", NOW + timedelta(minutes=minuto))
        turn.attach_reply(f"resposta {minuto}", NOW + timedelta(minutes=minuto))
        turn.attach_reply_audio(f"dev/{minuto}.mp3", NOW + timedelta(minutes=minuto))
        turn.complete(NOW + timedelta(minutes=minuto))
        await repository.update(turn)
    await db_session.commit()
    db_session.expunge_all()

    historico = await repository.list_by_session(sessao_persistida.id, limit=2)

    assert [t.transcript for t in historico] == ["fala 2", "fala 3"]


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


async def test_try_end_encerra_e_e_idempotente(
    db_session: AsyncSession, sessao_persistida: Session
) -> None:
    """A segunda chamada não pisa no `ended_at` da primeira (`COALESCE`)."""
    repository: SessionRepository = SqlAlchemySessionRepository(db_session)

    primeiro = await repository.try_end(
        sessao_persistida.id, NOW + timedelta(minutes=8)
    )
    await db_session.commit()
    segundo = await repository.try_end(sessao_persistida.id, NOW + timedelta(hours=1))
    await db_session.commit()

    assert primeiro == NOW + timedelta(minutes=8)
    assert segundo == primeiro  # o segundo instante NUNCA sobrescreve o primeiro


async def test_try_end_de_sessao_inexistente_e_erro_de_adapter(
    db_session: AsyncSession,
) -> None:
    repository: SessionRepository = SqlAlchemySessionRepository(db_session)

    with pytest.raises(RowNotFoundError):
        await repository.try_end(uuid4(), NOW)


async def test_duas_conexoes_concorrentes_nunca_produzem_dois_ended_at(
    database_url: str, sessao_persistida: Session
) -> None:
    """RNF4: a garantia real, contra duas conexões de banco DIFERENTES.

    `db_session` sozinho não prova nada aqui — as duas chamadas compartilhariam
    a mesma conexão e o mesmo snapshot de transação. O teste que importa é este:
    dois `AsyncSession` distintos, cada um vendo o outro só depois do commit, é
    o cenário real de dois `POST /end` concorrentes.
    """

    engine_a = create_engine(database_url)
    engine_b = create_engine(database_url)
    fabrica_a = create_session_factory(engine_a)
    fabrica_b = create_session_factory(engine_b)

    async def encerrar_em(fabrica: object, instante: datetime) -> datetime:
        async with fabrica() as sessao_db:  # type: ignore[operator]
            repository: SessionRepository = SqlAlchemySessionRepository(sessao_db)
            resultado = await repository.try_end(sessao_persistida.id, instante)
            await sessao_db.commit()
            return resultado

    resultado_a, resultado_b = await asyncio.gather(
        encerrar_em(fabrica_a, NOW + timedelta(minutes=1)),
        encerrar_em(fabrica_b, NOW + timedelta(minutes=2)),
    )

    await engine_a.dispose()
    await engine_b.dispose()

    assert resultado_a == resultado_b
    assert resultado_a in (NOW + timedelta(minutes=1), NOW + timedelta(minutes=2))


async def test_summary_for_soma_turns_e_agrupa_correcoes_por_tipo(
    db_session: AsyncSession, sessao_persistida: Session
) -> None:
    repository: SessionRepository = SqlAlchemySessionRepository(db_session)
    turns: TurnRepository = SqlAlchemyTurnRepository(db_session)
    um = sessao_persistida.start_turn(
        turn_id=uuid4(),
        input_audio_ref="dev/1.m4a",
        audio_duration=timedelta(seconds=10),
        now=NOW,
    )
    um.start_processing(NOW)
    um.attach_corrections([_correcao(0), _correcao(1)])
    dois = sessao_persistida.start_turn(
        turn_id=uuid4(),
        input_audio_ref="dev/2.m4a",
        audio_duration=timedelta(seconds=8),
        now=NOW,
    )
    dois.start_processing(NOW)
    dois.attach_corrections([_correcao(0)])
    await turns.add(um)
    await turns.add(dois)
    await db_session.commit()

    resumo = await repository.summary_for(sessao_persistida.id)

    assert resumo.turns == 2
    assert resumo.spoken == timedelta(seconds=18)
    assert resumo.corrections_by_type == {
        CorrectionType.GRAMMAR: 2,
        CorrectionType.PREPOSITION: 1,
    }


async def test_summary_for_sem_turn_nenhum_devolve_zeros(
    db_session: AsyncSession, sessao_persistida: Session
) -> None:
    """RF5: zero é dado, não ausência — a mesma régua do ADR-0021/0051."""
    repository: SessionRepository = SqlAlchemySessionRepository(db_session)

    resumo = await repository.summary_for(sessao_persistida.id)

    assert resumo.turns == 0
    assert resumo.spoken == timedelta(0)
    assert resumo.corrections_by_type == {}


async def test_student_novo_faz_roundtrip(db_session: AsyncSession) -> None:
    repository: StudentRepository = SqlAlchemyStudentRepository(db_session)
    student = Student(id=uuid4(), display_name="Ana Souza", created_at=NOW)

    await repository.add(student)
    await db_session.commit()
    db_session.expunge_all()

    assert await repository.get(student.id) == student


def test_id_do_student_dev_e_estavel() -> None:
    assert UUID("00000000-0000-0000-0000-000000000001") == DEV_STUDENT_ID


# -- trechos de áudio da resposta (ADR-0023) ---------------------------------


async def _turn_em_processamento(repository: TurnRepository, sessao: Session) -> Turn:
    turn = sessao.start_turn(
        turn_id=uuid4(),
        input_audio_ref="dev/entrada.m4a",
        audio_duration=timedelta(seconds=14),
        now=NOW,
    )
    turn.start_processing(NOW)
    await repository.add(turn)
    return turn


def _fala(turn: Turn, index: int) -> None:
    turn.append_audio_chunk(
        index=index,
        storage_key=f"aluno/sessao/{turn.id}/reply/{index:03d}.mp3",
        duration_seconds=1.25 + index,
        text=f"frase {index}",
        now=NOW + timedelta(milliseconds=400 * index),
    )


async def test_trechos_fazem_roundtrip_na_ordem_de_playback(
    db_session: AsyncSession, sessao_persistida: Session
) -> None:
    """A coleção volta ordenada por `index` — contrato de playback do ADR-0023."""
    repository: TurnRepository = SqlAlchemyTurnRepository(db_session)
    turn = await _turn_em_processamento(repository, sessao_persistida)
    _fala(turn, 0)
    _fala(turn, 1)
    _fala(turn, 2)

    await repository.update(turn)
    await db_session.commit()
    db_session.expunge_all()

    recarregado = await repository.get(turn.id)

    assert recarregado is not None
    assert [chunk.index for chunk in recarregado.audio_chunks] == [0, 1, 2]
    assert recarregado.audio_chunks[1].storage_key.endswith("reply/001.mp3")
    assert recarregado.audio_chunks[1].duration_seconds == 2.25
    # Igualdade por valor do @dataclass: cobre a coleção inteira de uma vez.
    assert recarregado == turn


async def test_update_acrescenta_trecho_sem_reinserir_os_anteriores(
    db_session: AsyncSession, sessao_persistida: Session
) -> None:
    """A cascata grava trecho a trecho: cada `update` é um append, não um replace."""
    repository: TurnRepository = SqlAlchemyTurnRepository(db_session)
    turn = await _turn_em_processamento(repository, sessao_persistida)
    _fala(turn, 0)
    await repository.update(turn)
    await db_session.commit()

    _fala(turn, 1)
    await repository.update(turn)
    await db_session.commit()
    db_session.expunge_all()

    recarregado = await repository.get(turn.id)

    assert recarregado is not None
    assert len(recarregado.audio_chunks) == 2
    assert recarregado.audio_chunks[0].text == "frase 0"


async def test_indice_repetido_e_recusado_pelo_banco(
    db_session: AsyncSession, sessao_persistida: Session
) -> None:
    """A mesma invariante do domínio, do outro lado — contra escrita concorrente.

    O domínio protege de lógica errada; a chave primária composta protege de dois
    processos que passaram cada um pela verificação do seu próprio lado.
    """
    repository: TurnRepository = SqlAlchemyTurnRepository(db_session)
    turn = await _turn_em_processamento(repository, sessao_persistida)
    _fala(turn, 0)
    await repository.update(turn)
    await db_session.commit()

    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "INSERT INTO turn_audio_chunks "
                "(turn_id, index, storage_key, duration_seconds, text, created_at) "
                "VALUES (:turn_id, 0, 'colidido.mp3', 1.0, 'colisão', :now)"
            ),
            {"turn_id": turn.id, "now": NOW},
        )
    await db_session.rollback()


async def test_falha_depois_da_entrega_preserva_os_trechos_no_banco(
    db_session: AsyncSession, sessao_persistida: Session
) -> None:
    """Critério de aceite do CARD-018, verificado do outro lado do mapeamento."""
    repository: TurnRepository = SqlAlchemyTurnRepository(db_session)
    turn = await _turn_em_processamento(repository, sessao_persistida)
    _fala(turn, 0)
    _fala(turn, 1)
    turn.fail("tts timeout", NOW)

    await repository.update(turn)
    await db_session.commit()
    db_session.expunge_all()

    recarregado = await repository.get(turn.id)

    assert recarregado is not None
    assert recarregado.status is TurnStatus.FAILED
    assert len(recarregado.audio_chunks) == 2
    assert recarregado.delivered_partially


async def test_gravar_sobre_estado_defasado_e_erro_de_adapter(
    db_session: AsyncSession, sessao_persistida: Session
) -> None:
    """Entidade com menos trechos que a linha não grava em silêncio."""
    repository: TurnRepository = SqlAlchemyTurnRepository(db_session)
    turn = await _turn_em_processamento(repository, sessao_persistida)
    _fala(turn, 0)
    await repository.update(turn)
    await db_session.commit()
    db_session.expunge_all()

    defasado = await repository.get(turn.id)
    assert defasado is not None
    defasado.audio_chunks.clear()  # simula quem carregou antes do trecho existir

    with pytest.raises(StaleTurnError):
        await repository.update(defasado)


# --- "Descartar" (CARD-032) -------------------------------------------------


async def test_try_discard_marca_e_e_idempotente(
    db_session: AsyncSession, sessao_persistida: Session
) -> None:
    repository: TurnRepository = SqlAlchemyTurnRepository(db_session)
    turn = await _turn_em_processamento(repository, sessao_persistida)
    await db_session.commit()

    primeiro = await repository.try_discard(turn.id, NOW)
    await db_session.commit()
    segundo = await repository.try_discard(turn.id, NOW + timedelta(hours=1))
    await db_session.commit()

    assert primeiro == NOW
    assert segundo == primeiro  # RNF1: a segunda chamada não move o instante


async def test_try_discard_recusa_turn_completo(
    db_session: AsyncSession, sessao_persistida: Session
) -> None:
    repository: TurnRepository = SqlAlchemyTurnRepository(db_session)
    turn = await _turn_em_processamento(repository, sessao_persistida)
    turn.attach_transcript("I go to the beach", NOW)
    turn.attach_reply("Nice!", NOW)
    turn.attach_reply_audio("dev/resposta.mp3", NOW)
    turn.complete(NOW)
    await repository.update(turn)
    await db_session.commit()

    resultado = await repository.try_discard(turn.id, NOW)

    assert resultado is None


async def test_try_discard_de_turn_inexistente_e_erro_de_adapter(
    db_session: AsyncSession,
) -> None:
    repository: TurnRepository = SqlAlchemyTurnRepository(db_session)

    with pytest.raises(RowNotFoundError):
        await repository.try_discard(uuid4(), NOW)


async def test_descarte_concorrente_com_a_conclusao_nunca_perde_nenhum_dos_dois(
    database_url: str, sessao_persistida: Session
) -> None:
    """RNF6: a corrida real, em conexões DIFERENTES — não sequencial disfarçada.

    Os dois desfechos legítimos dependem de QUEM o Postgres serializa
    primeiro (as duas `UPDATE` na mesma linha disputam o lock de linha):

    - o descarte comita enquanto o turn ainda não é `completed` → os dois
      fatos convivem (RF6: "descartado e completo ao mesmo tempo");
    - a conclusão comita primeiro → o descarte, ao rodar depois, vê
      ``status == completed`` e é recusado (RF2), como se tivesse chegado
      atrasado.

    O que NUNCA pode acontecer, e é o que este teste prova: a conclusão do
    worker **nunca se perde** (ela não depende de nada que o descarte
    escreva), e um descarte que **teve sucesso** nunca é apagado pela escrita
    do worker — que é exatamente o que `apply_turn` (ver o docstring)
    garante ao nunca copiar ``discarded_at`` de volta de uma entidade
    carregada antes do descarte acontecer.
    """
    engine_a = create_engine(database_url)
    engine_b = create_engine(database_url)
    fabrica_a = create_session_factory(engine_a)
    fabrica_b = create_session_factory(engine_b)

    async with fabrica_a() as sessao_a:
        repo_a: TurnRepository = SqlAlchemyTurnRepository(sessao_a)
        turn = await _turn_em_processamento(repo_a, sessao_persistida)
        await sessao_a.commit()

    async def descartar() -> datetime | None:
        async with fabrica_a() as sessao_db:
            repo: TurnRepository = SqlAlchemyTurnRepository(sessao_db)
            resultado = await repo.try_discard(turn.id, NOW)
            await sessao_db.commit()
            return resultado

    async def concluir() -> None:
        async with fabrica_b() as sessao_db:
            repo: TurnRepository = SqlAlchemyTurnRepository(sessao_db)
            # Carrega o turn ANTES do descarte poder ter acontecido — é o
            # cenário em que um `apply_turn` ingênuo apagaria o descarte.
            fresco = await repo.get(turn.id)
            assert fresco is not None
            fresco.attach_transcript("I go to the beach", NOW)
            fresco.attach_reply("Nice!", NOW)
            fresco.attach_reply_audio("dev/resposta.mp3", NOW)
            fresco.complete(NOW)
            await repo.update(fresco)
            await sessao_db.commit()

    resultado_do_descarte, _ = await asyncio.gather(descartar(), concluir())

    await engine_a.dispose()
    await engine_b.dispose()

    async with fabrica_a() as verificacao:
        final = await SqlAlchemyTurnRepository(verificacao).get(turn.id)

    assert final is not None
    # A conclusão do worker NUNCA se perde, não importa quem venceu a corrida.
    assert final.status is TurnStatus.COMPLETED
    # Um descarte que teve sucesso nunca é apagado pela escrita do worker.
    if resultado_do_descarte is not None:
        assert final.discarded_at == resultado_do_descarte


# --- idempotência do POST contra o banco de verdade (ADR-0042) --------------


async def test_a_chave_de_idempotencia_faz_roundtrip_e_e_consultavel(
    db_session: AsyncSession, sessao_persistida: Session
) -> None:
    repository: TurnRepository = SqlAlchemyTurnRepository(db_session)
    turn = sessao_persistida.start_turn(
        turn_id=uuid4(),
        input_audio_ref="dev/entrada.m4a",
        audio_duration=timedelta(seconds=4),
        now=NOW,
        idempotency_key="chave-do-cliente-abc",
    )
    await repository.add(turn)
    await db_session.commit()
    db_session.expunge_all()

    encontrado = await repository.get_by_idempotency_key("chave-do-cliente-abc")

    assert encontrado == turn
    assert await repository.get_by_idempotency_key("nunca-usada") is None


async def test_o_indice_unico_recusa_a_mesma_chave_duas_vezes(
    db_session: AsyncSession, sessao_persistida: Session
) -> None:
    """**A garantia que a consulta sozinha não dá** (ADR-0042, item 5).

    Duas requisições simultâneas passam as duas pela consulta "esta chave já
    existe?" e as duas tentam inserir. Quem impede a segunda é o índice, e é por
    isso que ele existe além do `SELECT`.
    """
    repository: TurnRepository = SqlAlchemyTurnRepository(db_session)
    for _ in range(2):
        await repository.add(
            sessao_persistida.start_turn(
                turn_id=uuid4(),
                input_audio_ref="dev/entrada.m4a",
                audio_duration=timedelta(seconds=4),
                now=NOW,
                idempotency_key="a-mesma-chave",
            )
        )

    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_o_indice_e_parcial_e_varios_turns_sem_chave_convivem(
    db_session: AsyncSession, sessao_persistida: Session
) -> None:
    """Turn criado fora da borda HTTP (worker, teste, backfill) tem chave nula.

    Se o índice não fosse parcial — ou se a coluna fosse `NOT NULL` — este
    cenário seria impossível, e o pipeline do CARD-009 quebraria.
    """
    repository: TurnRepository = SqlAlchemyTurnRepository(db_session)
    for _ in range(3):
        await repository.add(
            sessao_persistida.start_turn(
                turn_id=uuid4(),
                input_audio_ref="dev/entrada.m4a",
                audio_duration=timedelta(seconds=4),
                now=NOW,
            )
        )

    await db_session.commit()  # não levanta

    linhas = await db_session.execute(
        text("SELECT count(*) FROM turns WHERE idempotency_key IS NULL")
    )
    assert linhas.scalar_one() >= 3


async def test_o_unit_of_work_traduz_a_violacao_de_unicidade_para_erro_de_porta(
    db_session: AsyncSession, sessao_persistida: Session
) -> None:
    """A tradução que permite ao caso de uso tratar a corrida (ADR-0042).

    Sem ela, `application` teria de conhecer `sqlalchemy.exc.IntegrityError` —
    que o contrato de camada proíbe — ou capturar `Exception` genérica, que o
    ADR-0015 proíbe. E o desfecho seria 500 num duplo toque no botão.
    """
    repository: TurnRepository = SqlAlchemyTurnRepository(db_session)
    uow: UnitOfWork = SqlAlchemyUnitOfWork(db_session)
    for _ in range(2):
        await repository.add(
            sessao_persistida.start_turn(
                turn_id=uuid4(),
                input_audio_ref="dev/entrada.m4a",
                audio_duration=timedelta(seconds=4),
                now=NOW,
                idempotency_key="chave-em-corrida",
            )
        )

    with pytest.raises(ConflictingWriteError):
        await uow.commit()

    # E a sessão continua utilizável: o `rollback` do wrapper é o que permite ao
    # caso de uso RECONSULTAR quem chegou primeiro. Sem ele, a consulta seguinte
    # falharia com `PendingRollbackError`.
    assert await repository.get_by_idempotency_key("chave-em-corrida") is None


# --- correções persistidas (CARD-013) --------------------------------------


def _correcao(index: int) -> Correction:
    return Correction(
        index=index,
        type=CorrectionType.PREPOSITION if index else CorrectionType.GRAMMAR,
        original_excerpt=f"trecho errado {index}",
        corrected_form=f"trecho certo {index}",
        explanation=f"explicação {index}",
        severity=Severity.MAJOR if index else Severity.MINOR,
    )


async def test_duas_correcoes_persistem_ligadas_ao_turn(
    db_session: AsyncSession, sessao_persistida: Session
) -> None:
    """Critério de aceite do CARD-013, contra Postgres real (ADR-0018).

    A última asserção é a que cobre mais: ``recarregado == turn`` compara a
    **lista inteira** de correções com um ``==`` só, e isso só funciona porque
    ``Correction`` é ``@dataclass(frozen=True)`` — o ``__eq__`` gerado é por
    valor, não por identidade de objeto. Um campo que voltasse errado do banco
    (o enum guardado pelo NOME em vez do valor, por exemplo) reprova aqui sem
    precisar de uma asserção por campo.
    """
    repository: TurnRepository = SqlAlchemyTurnRepository(db_session)
    turn = await _turn_em_processamento(repository, sessao_persistida)
    turn.attach_reply("Nice!", NOW)
    turn.attach_corrections([_correcao(0), _correcao(1)])

    await repository.update(turn)
    await db_session.commit()
    db_session.expunge_all()

    recarregado = await repository.get(turn.id)

    assert recarregado is not None
    assert len(recarregado.corrections) == 2
    assert [c.index for c in recarregado.corrections] == [0, 1]
    assert recarregado.corrections[1].type is CorrectionType.PREPOSITION
    assert recarregado.corrections[1].severity is Severity.MAJOR
    assert recarregado == turn


async def test_o_enum_e_gravado_com_o_valor_do_membro_nao_com_o_nome(
    db_session: AsyncSession, sessao_persistida: Session
) -> None:
    """``values_callable``: o banco guarda ``word_order``, não ``WORD_ORDER``.

    O roundtrip acima passaria dos dois jeitos — o SQLAlchemy converte na ida e
    na volta. O que quebra sem isto é tudo que lê o banco **por fora** da
    aplicação, e o JSON do contrato, que trafega o valor. Por isso este teste
    desce a SQL crua: é a única forma de ver o que está gravado de fato.
    """
    repository: TurnRepository = SqlAlchemyTurnRepository(db_session)
    turn = await _turn_em_processamento(repository, sessao_persistida)
    turn.attach_reply("Nice!", NOW)
    turn.attach_corrections(
        [
            Correction(
                index=0,
                type=CorrectionType.WORD_ORDER,
                original_excerpt="always I go",
                corrected_form="I always go",
                explanation="Adverb goes after the subject.",
                severity=Severity.MODERATE,
            )
        ]
    )
    await repository.update(turn)
    await db_session.commit()

    # Escopado pelo turn: o banco do container é compartilhado pela suíte
    # inteira (fixture de sessão), então um `SELECT` sem `WHERE` leria também as
    # correções dos outros testes.
    gravado = await db_session.execute(
        text(
            "SELECT type::text, severity::text FROM turn_corrections "
            "WHERE turn_id = :id"
        ),
        {"id": turn.id},
    )

    assert [tuple(linha) for linha in gravado.all()] == [("word_order", "moderate")]


async def test_o_delete_do_turn_leva_as_correcoes_junto(
    db_session: AsyncSession, sessao_persistida: Session
) -> None:
    """``ondelete=CASCADE`` no banco, não só ``delete-orphan`` no ORM.

    A diferença aparece num ``DELETE`` que não passa pelo ORM — o delete de
    conta do CARD-017, ou uma limpeza feita na mão. Sem a regra no Postgres, ele
    falharia por violação de foreign key.
    """
    repository: TurnRepository = SqlAlchemyTurnRepository(db_session)
    turn = await _turn_em_processamento(repository, sessao_persistida)
    turn.attach_reply("Nice!", NOW)
    turn.attach_corrections([_correcao(0)])
    await repository.update(turn)
    await db_session.commit()

    await db_session.execute(text("DELETE FROM turns WHERE id = :id"), {"id": turn.id})
    await db_session.commit()

    restantes = await db_session.execute(
        text("SELECT count(*) FROM turn_corrections WHERE turn_id = :id"),
        {"id": turn.id},
    )
    assert restantes.scalar_one() == 0


# --- CARD-014: o custo real, contra Postgres de verdade --------------------


def _evento_de(
    turn_id: UUID,
    student_id: UUID,
    *,
    quando: datetime,
    falado: timedelta = timedelta(seconds=4),
    custo: Decimal | None = Decimal("0.00198400"),
) -> UsageEvent:
    return UsageEvent(
        turn_id=turn_id,
        student_id=student_id,
        occurred_at=quando,
        llm_model="claude-haiku-4-5-20251001",
        llm_input_tokens=1084,
        llm_cache_creation_tokens=0,
        llm_cache_read_tokens=0,
        llm_output_tokens=180,
        stt_audio_duration=falado,
        stt_provider="faster_whisper",
        stt_confidence=-0.2,
        stt_no_speech=0.01,
        tts_chars=91,
        tts_provider="piper",
        estimated_cost_usd=custo,
    )


async def _turn_gravado(
    db_session: AsyncSession, sessao: Session, *, quando: datetime = NOW
) -> Turn:
    turns: TurnRepository = SqlAlchemyTurnRepository(db_session)
    turn = sessao.start_turn(
        turn_id=uuid4(),
        input_audio_ref="dev/entrada.m4a",
        audio_duration=timedelta(seconds=4),
        now=quando,
    )
    await turns.add(turn)
    await db_session.commit()
    return turn


@pytest.fixture
async def aluno_isolado(db_session: AsyncSession) -> tuple[Student, Session]:
    """Um Student e uma Session **novos**, só para os testes de agregação.

    Os demais testes deste arquivo reusam o Student de desenvolvimento, e podem:
    eles leem por `turn_id`. Agregação não pode — o container é de escopo de
    sessão e as linhas de um teste ficam visíveis para o seguinte, o que fez as
    três somas darem 7 onde o teste esperava 1. Isolar por aluno é mais barato
    que limpar tabela entre casos, e reproduz melhor a realidade: a query é por
    `student_id` justamente porque há outros alunos no banco.
    """
    student = Student(id=uuid4(), display_name="Aluno de agregação", created_at=NOW)
    students: StudentRepository = SqlAlchemyStudentRepository(db_session)
    await students.add(student)
    # Commit ANTES da sessão, e não os dois no mesmo flush: não há
    # `relationship` entre `StudentRow` e `SessionRow` (a FK existe, o
    # relacionamento não), então o SQLAlchemy não conhece a dependência e pode
    # ordenar o INSERT de `sessions` primeiro — `ForeignKeyViolationError`
    # medido nesta sessão. É o contraste com o EF Core, onde o grafo de
    # navegação daria a ordem de graça.
    await db_session.commit()
    sessao = Session(id=uuid4(), student_id=student.id, started_at=NOW)
    sessions: SessionRepository = SqlAlchemySessionRepository(db_session)
    await sessions.add(sessao)
    await db_session.commit()
    return student, sessao


async def test_roundtrip_do_usage_event_preserva_decimal_e_intervalo(
    db_session: AsyncSession, sessao_persistida: Session
) -> None:
    """O que só o Postgres pode quebrar: NUMERIC virando float e INTERVAL virando int.

    A comparação é a entidade inteira com um `==` só — possível porque
    `frozen=True` dá `__eq__` por valor. Um laço campo a campo passaria a
    esquecer o campo novo no dia em que alguém acrescentasse um.
    """
    repository: UsageEventRepository = SqlAlchemyUsageEventRepository(db_session)
    turn = await _turn_gravado(db_session, sessao_persistida)
    evento = _evento_de(turn.id, sessao_persistida.student_id, quando=NOW)

    await repository.add(evento)
    await db_session.commit()
    db_session.expunge_all()  # força ler do banco, não do cache de identidade

    recarregado = await repository.get(turn.id)

    assert recarregado == evento
    assert recarregado is not None
    # As asserções que o `==` não deixa ver, e que são o motivo de o teste rodar
    # contra Postgres em vez de contra um dublê:
    assert isinstance(recarregado.estimated_cost_usd, Decimal)
    assert recarregado.estimated_cost_usd == Decimal("0.00198400")
    assert recarregado.stt_audio_duration == timedelta(seconds=4)
    assert recarregado.occurred_at.tzinfo is not None  # TIMESTAMPTZ, não ingênuo


async def test_as_tres_contagens_de_entrada_voltam_do_banco_como_zero(
    db_session: AsyncSession, sessao_persistida: Session
) -> None:
    """Zero é dado, não ausência (ADR-0021): as colunas são `NOT NULL`."""
    repository: UsageEventRepository = SqlAlchemyUsageEventRepository(db_session)
    turn = await _turn_gravado(db_session, sessao_persistida)

    await repository.add(_evento_de(turn.id, sessao_persistida.student_id, quando=NOW))
    await db_session.commit()
    db_session.expunge_all()

    recarregado = await repository.get(turn.id)

    assert recarregado is not None
    assert recarregado.llm_cache_creation_tokens == 0
    assert recarregado.llm_cache_read_tokens == 0


async def test_custo_desconhecido_volta_nulo_e_nao_zero(
    db_session: AsyncSession, sessao_persistida: Session
) -> None:
    """A coluna é nulável de propósito, e o nulo tem significado próprio.

    `NULL` = "não sabemos precificar este modelo"; `0` = o custo verdadeiro do
    STT e do TTS locais. Se o banco convertesse um no outro, o kill switch do
    CARD-015 leria como grátis um turn cujo custo ninguém conhece.
    """
    repository: UsageEventRepository = SqlAlchemyUsageEventRepository(db_session)
    turn = await _turn_gravado(db_session, sessao_persistida)

    await repository.add(
        _evento_de(turn.id, sessao_persistida.student_id, quando=NOW, custo=None)
    )
    await db_session.commit()
    db_session.expunge_all()

    recarregado = await repository.get(turn.id)

    assert recarregado is not None
    assert recarregado.estimated_cost_usd is None


async def test_um_turn_so_pode_ter_um_evento_de_custo(
    db_session: AsyncSession, sessao_persistida: Session
) -> None:
    """A chave primária é `turn_id`, e é ela que impede a soma de dobrar.

    Sem a PK, uma segunda escrita passaria em silêncio e todo total daquele aluno
    contaria o mesmo turn duas vezes — um erro que nenhum teste de resultado
    final pegaria.
    """
    repository: UsageEventRepository = SqlAlchemyUsageEventRepository(db_session)
    uow: UnitOfWork = SqlAlchemyUnitOfWork(db_session)
    turn = await _turn_gravado(db_session, sessao_persistida)

    await repository.add(_evento_de(turn.id, sessao_persistida.student_id, quando=NOW))
    await uow.commit()
    await repository.add(_evento_de(turn.id, sessao_persistida.student_id, quando=NOW))

    with pytest.raises(ConflictingWriteError):
        await uow.commit()


async def test_agregacao_por_student_soma_em_minutos_e_em_turns(
    db_session: AsyncSession, aluno_isolado: tuple[Student, Session]
) -> None:
    """Critério de aceite: 3 turns de 2 students, somados no banco.

    As duas unidades juntas porque a unidade da cota ainda não foi decidida — a
    análise de custo §8 mediu 3x de divergência entre elas, e uma agregação que
    devolvesse só uma responderia a pergunta antes de ela ser feita.
    """
    _, sessao_persistida = aluno_isolado
    repository: UsageEventRepository = SqlAlchemyUsageEventRepository(db_session)
    sessions: SessionRepository = SqlAlchemySessionRepository(db_session)
    students: StudentRepository = SqlAlchemyStudentRepository(db_session)

    # O segundo aluno, com sessão própria: a agregação tem de ignorá-lo por
    # completo, e sem ele o teste passaria mesmo com o `WHERE` errado.
    outro = Student(id=uuid4(), display_name="Outro", created_at=NOW)
    await students.add(outro)
    await db_session.commit()  # antes da sessão: ver a nota em `aluno_isolado`
    sessao_do_outro = Session(id=uuid4(), student_id=outro.id, started_at=NOW)
    await sessions.add(sessao_do_outro)
    await db_session.commit()

    dois = [
        await _turn_gravado(db_session, sessao_persistida),
        await _turn_gravado(db_session, sessao_persistida),
    ]
    do_outro = await _turn_gravado(db_session, sessao_do_outro)

    for i, turn in enumerate(dois):
        await repository.add(
            _evento_de(
                turn.id,
                sessao_persistida.student_id,
                quando=NOW + timedelta(minutes=i),
                falado=timedelta(seconds=4),
            )
        )
    await repository.add(
        _evento_de(
            do_outro.id,
            outro.id,
            quando=NOW,
            falado=timedelta(seconds=30),
            custo=Decimal("0.01000000"),
        )
    )
    await db_session.commit()

    totais = await repository.totals_for_student(
        sessao_persistida.student_id, since=NOW, until=NOW + timedelta(days=1)
    )

    assert totais.turns == 2
    assert totais.spoken == timedelta(seconds=8)
    assert totais.cost_usd == Decimal("0.00396800")
    assert totais.unpriced_turns == 0
    # O outro aluno permanece intacto — a prova de que o `WHERE student_id` está
    # de fato filtrando, e não somando o produto inteiro.
    do_outro_totais = await repository.totals_for_student(
        outro.id, since=NOW, until=NOW + timedelta(days=1)
    )
    assert do_outro_totais.turns == 1
    assert do_outro_totais.spoken == timedelta(seconds=30)


async def test_turno_sem_preco_conta_como_turn_mas_nao_soma_custo(
    db_session: AsyncSession, aluno_isolado: tuple[Student, Session]
) -> None:
    """Custo subestimado não pode ser indistinguível de custo baixo.

    A linha entra em `turns` e em `spoken` (o aluno falou de verdade) e fica de
    fora de `cost_usd` — somá-la como zero mentiria dizendo que aquele turn foi
    grátis. `unpriced_turns` é quem torna a lacuna visível.
    """
    _, sessao_persistida = aluno_isolado
    repository: UsageEventRepository = SqlAlchemyUsageEventRepository(db_session)
    com_preco = await _turn_gravado(db_session, sessao_persistida)
    sem_preco = await _turn_gravado(db_session, sessao_persistida)

    await repository.add(
        _evento_de(com_preco.id, sessao_persistida.student_id, quando=NOW)
    )
    await repository.add(
        _evento_de(sem_preco.id, sessao_persistida.student_id, quando=NOW, custo=None)
    )
    await db_session.commit()

    totais = await repository.totals_for_student(
        sessao_persistida.student_id, since=NOW, until=NOW + timedelta(days=1)
    )

    assert totais.turns == 2
    assert totais.cost_usd == Decimal("0.00198400")
    assert totais.unpriced_turns == 1


async def test_aluno_sem_consumo_na_janela_recebe_zeros_e_nao_nulo(
    db_session: AsyncSession, sessao_persistida: Session
) -> None:
    """`SUM` de conjunto vazio devolve `NULL` — é o que os `coalesce` cobrem.

    Sem eles, o primeiro turn do dia (o caso mais comum de todos) quebraria a
    decisão de cota do CARD-015 justamente no caminho feliz.
    """
    repository: UsageEventRepository = SqlAlchemyUsageEventRepository(db_session)

    totais = await repository.totals_for_student(
        uuid4(), since=NOW, until=NOW + timedelta(days=1)
    )

    assert totais.turns == 0
    assert totais.spoken == timedelta(0)
    assert totais.cost_usd == Decimal(0)


async def test_a_janela_e_meio_aberta_e_nao_conta_o_mesmo_turn_duas_vezes(
    db_session: AsyncSession, aluno_isolado: tuple[Student, Session]
) -> None:
    """`>= since` e `< until`: o turn da virada pertence a um dia só."""
    _, sessao_persistida = aluno_isolado
    repository: UsageEventRepository = SqlAlchemyUsageEventRepository(db_session)
    turn = await _turn_gravado(db_session, sessao_persistida)
    await repository.add(_evento_de(turn.id, sessao_persistida.student_id, quando=NOW))
    await db_session.commit()

    dentro = await repository.totals_for_student(
        sessao_persistida.student_id, since=NOW, until=NOW + timedelta(seconds=1)
    )
    fora = await repository.totals_for_student(
        sessao_persistida.student_id,
        since=NOW + timedelta(seconds=1),
        until=NOW + timedelta(days=1),
    )

    assert dentro.turns == 1
    assert fora.turns == 0


# -- varredura de turns travados (CARD-025) ----------------------------------


async def test_list_stale_acha_o_queued_que_o_worker_nunca_pegou(
    db_session: AsyncSession, sessao_persistida: Session
) -> None:
    """O caso que uma query sem `coalesce` deixaria invisível para sempre.

    Um turn `queued` tem `started_processing_at` NULO, e `NULL < :before` é
    `NULL` em SQL — não `true`. Sem o `coalesce`, este turn nunca apareceria, e
    o teste do caso `processing` passaria mesmo assim: metade do card verde,
    metade do buraco aberto.
    """
    repository: TurnRepository = SqlAlchemyTurnRepository(db_session)
    turn = sessao_persistida.start_turn(
        turn_id=uuid4(),
        input_audio_ref="dev/entrada.m4a",
        audio_duration=timedelta(seconds=4),
        now=NOW - timedelta(minutes=10),
    )
    await repository.add(turn)
    await db_session.commit()

    achados = await repository.list_stale(before=NOW - timedelta(minutes=5), limit=10)

    assert turn.id in achados


async def test_list_stale_ignora_o_que_esta_dentro_do_prazo_e_o_que_terminou(
    db_session: AsyncSession, sessao_persistida: Session
) -> None:
    """Três turns, um só travado. É a query inteira exercitada de uma vez."""
    repository: TurnRepository = SqlAlchemyTurnRepository(db_session)

    travado = await _turn_parado(
        repository, sessao_persistida, NOW - timedelta(minutes=9)
    )
    recente = await _turn_parado(
        repository, sessao_persistida, NOW - timedelta(minutes=1)
    )
    terminado = await _turn_parado(
        repository, sessao_persistida, NOW - timedelta(hours=2)
    )
    terminado.fail("já resolvido", NOW - timedelta(hours=2))
    await repository.update(terminado)
    await db_session.commit()

    achados = await repository.list_stale(before=NOW - timedelta(minutes=5), limit=10)

    assert travado.id in achados
    assert recente.id not in achados
    assert terminado.id not in achados


async def test_list_stale_devolve_os_mais_antigos_primeiro_e_respeita_o_limite(
    db_session: AsyncSession, sessao_persistida: Session
) -> None:
    """Sem `order_by` o Postgres não promete ordem nenhuma.

    Com lote limitado, isso não é detalhe: o turn travado há mais tempo poderia
    ficar de fora de toda rodada, para sempre — e a varredura convergiria em
    todos os turns menos justamente o mais antigo.
    """
    repository: TurnRepository = SqlAlchemyTurnRepository(db_session)
    mais_velho = await _turn_parado(
        repository, sessao_persistida, NOW - timedelta(hours=3)
    )
    do_meio = await _turn_parado(
        repository, sessao_persistida, NOW - timedelta(hours=2)
    )
    await _turn_parado(repository, sessao_persistida, NOW - timedelta(hours=1))
    await db_session.commit()

    achados = await repository.list_stale(before=NOW - timedelta(minutes=5), limit=2)

    assert achados == [mais_velho.id, do_meio.id]


async def _turn_parado(
    repository: TurnRepository, sessao: Session, quando: datetime
) -> Turn:
    """Um turn em `processing` desde `quando`, gravado mas não comitado."""
    turn = sessao.start_turn(
        turn_id=uuid4(),
        input_audio_ref="dev/entrada.m4a",
        audio_duration=timedelta(seconds=4),
        now=quando,
    )
    turn.start_processing(quando)
    await repository.add(turn)
    return turn


# --- traduções sob demanda (CARD-036) ---------------------------------------


def _traducao(turn_id: UUID, *, target: TranslationTarget, index: int) -> Translation:
    return Translation(
        turn_id=turn_id,
        target=target,
        index=index,
        text="Qual praia você foi?",
        model="claude-haiku-4-5-20251001",
        created_at=NOW,
        estimated_cost_usd=Decimal("0.00016000"),
    )


async def test_traducao_faz_roundtrip_preservando_decimal_e_enum(
    db_session: AsyncSession, sessao_persistida: Session
) -> None:
    """O que só o Postgres pode quebrar: NUMERIC virando float e enum pelo nome."""
    turns: TurnRepository = SqlAlchemyTurnRepository(db_session)
    repository: TranslationRepository = SqlAlchemyTranslationRepository(db_session)
    turn = await _turn_em_processamento(turns, sessao_persistida)
    await db_session.commit()

    original = _traducao(turn.id, target=TranslationTarget.REPLY, index=0)
    await repository.add(original)
    await db_session.commit()
    db_session.expunge_all()

    recarregada = await repository.get(turn.id, TranslationTarget.REPLY, 0)

    # Igualdade por valor do `frozen=True`: cobre os sete campos de uma vez.
    assert recarregada == original
    assert recarregada is not None
    assert isinstance(recarregada.estimated_cost_usd, Decimal)
    assert recarregada.created_at.tzinfo is not None  # TIMESTAMPTZ, não ingênuo


async def test_o_enum_do_alvo_e_gravado_com_o_valor_e_nao_com_o_nome(
    db_session: AsyncSession, sessao_persistida: Session
) -> None:
    """`values_callable`: o banco guarda 'correction', não 'CORRECTION'."""
    turns: TurnRepository = SqlAlchemyTurnRepository(db_session)
    repository: TranslationRepository = SqlAlchemyTranslationRepository(db_session)
    turn = await _turn_em_processamento(turns, sessao_persistida)
    await db_session.commit()

    await repository.add(
        _traducao(turn.id, target=TranslationTarget.CORRECTION, index=2)
    )
    await db_session.commit()

    gravado = await db_session.execute(
        text("SELECT target::text FROM turn_translations WHERE turn_id = :id"),
        {"id": turn.id},
    )
    assert gravado.scalar_one() == "correction"


async def test_a_chave_composta_recusa_a_mesma_traducao_duas_vezes(
    db_session: AsyncSession, sessao_persistida: Session
) -> None:
    """**A garantia que a consulta sozinha não dá** (RF4, mesmo desenho do ADR-0042).

    Duas requisições simultâneas passam as duas pelo `get` que devolve `None` e
    as duas tentam gravar. Quem impede a segunda é a chave primária — e é por
    isso que ela existe além do `SELECT`.
    """
    turns: TurnRepository = SqlAlchemyTurnRepository(db_session)
    repository: TranslationRepository = SqlAlchemyTranslationRepository(db_session)
    uow: UnitOfWork = SqlAlchemyUnitOfWork(db_session)
    turn = await _turn_em_processamento(turns, sessao_persistida)
    await db_session.commit()

    for _ in range(2):
        await repository.add(
            _traducao(turn.id, target=TranslationTarget.REPLY, index=0)
        )

    with pytest.raises(ConflictingWriteError):
        await uow.commit()


async def test_resposta_e_correcao_do_mesmo_turn_convivem(
    db_session: AsyncSession, sessao_persistida: Session
) -> None:
    """A chave é `(turn_id, target, index)`: alvos diferentes não colidem."""
    turns: TurnRepository = SqlAlchemyTurnRepository(db_session)
    repository: TranslationRepository = SqlAlchemyTranslationRepository(db_session)
    turn = await _turn_em_processamento(turns, sessao_persistida)
    await db_session.commit()

    await repository.add(_traducao(turn.id, target=TranslationTarget.REPLY, index=0))
    await repository.add(
        _traducao(turn.id, target=TranslationTarget.CORRECTION, index=0)
    )
    await db_session.commit()  # não levanta

    assert await repository.get(turn.id, TranslationTarget.REPLY, 0) is not None
    assert await repository.get(turn.id, TranslationTarget.CORRECTION, 0) is not None


async def test_traducao_inexistente_devolve_none(
    db_session: AsyncSession,
) -> None:
    repository: TranslationRepository = SqlAlchemyTranslationRepository(db_session)

    assert await repository.get(uuid4(), TranslationTarget.REPLY, 0) is None


async def test_o_delete_do_turn_leva_as_traducoes_junto(
    db_session: AsyncSession, sessao_persistida: Session
) -> None:
    """`ondelete=CASCADE` no banco: o delete de conta do CARD-017 ignora esta tabela."""
    turns: TurnRepository = SqlAlchemyTurnRepository(db_session)
    repository: TranslationRepository = SqlAlchemyTranslationRepository(db_session)
    turn = await _turn_em_processamento(turns, sessao_persistida)
    # Commit ANTES da tradução: não há `relationship` entre `TurnRow` e
    # `TranslationRow` (a FK existe, o relacionamento não), então o SQLAlchemy
    # não conhece a dependência e pode ordenar o INSERT da tradução primeiro —
    # a mesma armadilha anotada na fixture `aluno_isolado`.
    await db_session.commit()
    await repository.add(_traducao(turn.id, target=TranslationTarget.REPLY, index=0))
    await db_session.commit()

    await db_session.execute(text("DELETE FROM turns WHERE id = :id"), {"id": turn.id})
    await db_session.commit()

    restantes = await db_session.execute(
        text("SELECT count(*) FROM turn_translations WHERE turn_id = :id"),
        {"id": turn.id},
    )
    assert restantes.scalar_one() == 0


# --- listagem de sessões (CARD-030) -----------------------------------------


@contextmanager
def _contando_queries(db_session: AsyncSession) -> Iterator[list[str]]:
    """Conta os SELECTs que saíram de verdade — o "log de SQL" do RNF1.

    `event.listen` sobre `before_cursor_execute` é o gancho do SQLAlchemy que
    vê a instrução **depois** de compilada e **antes** de ir ao driver: é o
    ponto onde um N+1 fica visível, porque cada iteração do laço aparece como
    uma linha a mais.

    O alvo é o que `get_bind()` devolve — o motor **síncrono** que o
    `AsyncSession` embrulha. O sistema de eventos do SQLAlchemy é do síncrono;
    registrar no `AsyncEngine` não veria nada, e o silêncio pareceria "zero
    queries".
    """
    executadas: list[str] = []

    def registrar(
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        del conn, cursor, parameters, context, executemany
        executadas.append(statement)

    motor = db_session.get_bind()
    event.listen(motor, "before_cursor_execute", registrar)
    try:
        yield executadas
    finally:
        event.remove(motor, "before_cursor_execute", registrar)


async def _sessao_com_turns(
    db_session: AsyncSession, student_id: UUID, *, quando: datetime, turns: int
) -> Session:
    sessions: SessionRepository = SqlAlchemySessionRepository(db_session)
    repository: TurnRepository = SqlAlchemyTurnRepository(db_session)
    sessao = Session(id=uuid4(), student_id=student_id, started_at=quando)
    await sessions.add(sessao)
    await db_session.commit()  # antes dos turns: ver a nota em `aluno_isolado`
    for i in range(turns):
        turn = sessao.start_turn(
            turn_id=uuid4(),
            input_audio_ref=f"dev/{i}.m4a",
            audio_duration=timedelta(seconds=30),
            now=quando,
        )
        turn.start_processing(quando)
        turn.attach_reply("Nice!", quando)
        turn.attach_corrections([_correcao(0), _correcao(1)])
        await repository.add(turn)
    await db_session.commit()
    return sessao


async def test_listagem_ordena_da_mais_recente_e_agrega_no_banco(
    db_session: AsyncSession, aluno_isolado: tuple[Student, Session]
) -> None:
    """Critério de aceite: 3 sessões ordenadas, com contagens corretas.

    A agregação de correções é o risco nº 1 do card (dois níveis de `JOIN`):
    dois turns com duas correções cada devem dar **4 correções e 60 s**, nunca
    4 correções e 120 s — que é o que um `JOIN` triplo produziria ao
    multiplicar o áudio pelo número de correções.
    """
    student, _ = aluno_isolado
    repository: SessionRepository = SqlAlchemySessionRepository(db_session)
    velha = await _sessao_com_turns(
        db_session, student.id, quando=NOW - timedelta(days=3), turns=1
    )
    nova = await _sessao_com_turns(
        db_session, student.id, quando=NOW - timedelta(hours=1), turns=2
    )

    listagem = await repository.list_for_student(
        student.id, since=NOW - timedelta(days=30)
    )

    ids = [d.id for d in listagem]
    assert ids.index(nova.id) < ids.index(velha.id)
    da_nova = next(d for d in listagem if d.id == nova.id)
    assert da_nova.turns == 2
    assert da_nova.spoken == timedelta(minutes=1)  # 2 x 30 s, NÃO 4 x 30 s
    assert da_nova.corrections == 4


async def test_o_numero_de_queries_nao_cresce_com_o_numero_de_sessoes(
    db_session: AsyncSession, aluno_isolado: tuple[Student, Session]
) -> None:
    """**O critério de aceite do RNF1**, provado no log de SQL.

    O `lazy="raise_on_sql"` protegeria contra tocar uma coleção sem querer; ele
    não protege contra um laço que chama o repositório por linha. Só a contagem
    protege — e ela compara 1 sessão com 6.
    """
    student, _ = aluno_isolado
    repository: SessionRepository = SqlAlchemySessionRepository(db_session)
    await _sessao_com_turns(db_session, student.id, quando=NOW, turns=1)

    with _contando_queries(db_session) as com_uma:
        poucas = await repository.list_for_student(
            student.id, since=NOW - timedelta(days=30)
        )
    queries_com_uma = len(com_uma)

    for i in range(5):
        await _sessao_com_turns(
            db_session, student.id, quando=NOW - timedelta(hours=i + 1), turns=2
        )

    with _contando_queries(db_session) as com_seis:
        listagem = await repository.list_for_student(
            student.id, since=NOW - timedelta(days=30)
        )

    # A lista cresceu de verdade (senão a comparação de queries não diria nada)…
    assert len(listagem) == len(poucas) + 5
    # …e mesmo assim o número de queries é o MESMO. É este par de asserções que
    # separa "não tem N+1" de "o teste não exercitou nada".
    assert len(com_seis) == queries_com_uma


async def test_sessao_sem_turn_nenhum_aparece_na_listagem(
    db_session: AsyncSession, aluno_isolado: tuple[Student, Session]
) -> None:
    """`outerjoin` e não `join`: com o interno ela sumiria, em silêncio (RF4)."""
    student, _ = aluno_isolado
    sessions: SessionRepository = SqlAlchemySessionRepository(db_session)
    vazia = Session(id=uuid4(), student_id=student.id, started_at=NOW)
    await sessions.add(vazia)
    await db_session.commit()

    listagem = await sessions.list_for_student(
        student.id, since=NOW - timedelta(days=30)
    )

    digest = next(d for d in listagem if d.id == vazia.id)
    assert digest.turns == 0
    assert digest.spoken == timedelta(0)
    assert digest.corrections == 0
    assert digest.last_turn_at is None


async def test_a_listagem_nao_ve_sessao_de_outro_aluno(
    db_session: AsyncSession, aluno_isolado: tuple[Student, Session]
) -> None:
    student, _ = aluno_isolado
    sessions: SessionRepository = SqlAlchemySessionRepository(db_session)
    students: StudentRepository = SqlAlchemyStudentRepository(db_session)
    outro = Student(id=uuid4(), display_name="Outro", created_at=NOW)
    await students.add(outro)
    await db_session.commit()
    await _sessao_com_turns(db_session, outro.id, quando=NOW, turns=1)

    listagem = await sessions.list_for_student(
        student.id, since=NOW - timedelta(days=30)
    )

    assert all(d.id != outro.id for d in listagem)


async def test_a_janela_exclui_o_que_e_mais_velho(
    db_session: AsyncSession, aluno_isolado: tuple[Student, Session]
) -> None:
    student, _ = aluno_isolado
    repository: SessionRepository = SqlAlchemySessionRepository(db_session)
    antiga = await _sessao_com_turns(
        db_session, student.id, quando=NOW - timedelta(days=40), turns=1
    )

    listagem = await repository.list_for_student(
        student.id, since=NOW - timedelta(days=30)
    )

    assert all(d.id != antiga.id for d in listagem)


# --- varredura de sessões inativas (CARD-034) -------------------------------


async def _sessao_aberta(
    db_session: AsyncSession, student_id: UUID, *, aberta_em: datetime
) -> Session:
    sessions: SessionRepository = SqlAlchemySessionRepository(db_session)
    sessao = Session(id=uuid4(), student_id=student_id, started_at=aberta_em)
    await sessions.add(sessao)
    await db_session.commit()
    return sessao


async def _turn_em(
    db_session: AsyncSession, sessao: Session, *, quando: datetime, concluido: bool
) -> Turn:
    repository: TurnRepository = SqlAlchemyTurnRepository(db_session)
    turn = sessao.start_turn(
        turn_id=uuid4(),
        input_audio_ref="dev/entrada.m4a",
        audio_duration=timedelta(seconds=4),
        now=quando,
    )
    turn.start_processing(quando)
    if concluido:
        turn.attach_transcript("hi", quando)
        turn.attach_reply("Nice!", quando)
        turn.attach_reply_audio("dev/resposta.mp3", quando)
        turn.complete(quando)
    await repository.add(turn)
    await db_session.commit()
    return turn


async def test_list_inactive_acha_a_sessao_parada_e_ignora_a_recente(
    db_session: AsyncSession, aluno_isolado: tuple[Student, Session]
) -> None:
    student, _ = aluno_isolado
    repository: SessionRepository = SqlAlchemySessionRepository(db_session)
    parada = await _sessao_aberta(
        db_session, student.id, aberta_em=NOW - timedelta(hours=5)
    )
    await _turn_em(db_session, parada, quando=NOW - timedelta(hours=4), concluido=True)
    recente = await _sessao_aberta(
        db_session, student.id, aberta_em=NOW - timedelta(hours=5)
    )
    await _turn_em(
        db_session, recente, quando=NOW - timedelta(minutes=2), concluido=True
    )

    candidatas = await repository.list_inactive(
        before=NOW - timedelta(minutes=30), limit=50
    )

    assert parada.id in candidatas
    assert recente.id not in candidatas


async def test_list_inactive_pega_a_sessao_sem_turn_nenhum(
    db_session: AsyncSession, aluno_isolado: tuple[Student, Session]
) -> None:
    """RF2: sem turn, o marco é o `started_at`.

    Sem o `coalesce` do adapter, o marco seria `NULL` — e `NULL < :before` é
    `NULL`, não `true`. Esta sessão nunca apareceria, em silêncio.
    """
    student, _ = aluno_isolado
    repository: SessionRepository = SqlAlchemySessionRepository(db_session)
    vazia = await _sessao_aberta(
        db_session, student.id, aberta_em=NOW - timedelta(hours=2)
    )

    candidatas = await repository.list_inactive(
        before=NOW - timedelta(minutes=30), limit=50
    )

    assert vazia.id in candidatas


async def test_list_inactive_exclui_sessao_com_turn_em_processamento(
    db_session: AsyncSession, aluno_isolado: tuple[Student, Session]
) -> None:
    """RF3, no `HAVING` com `FILTER` — não num segundo round-trip."""
    student, _ = aluno_isolado
    repository: SessionRepository = SqlAlchemySessionRepository(db_session)
    esperando = await _sessao_aberta(
        db_session, student.id, aberta_em=NOW - timedelta(hours=6)
    )
    await _turn_em(
        db_session, esperando, quando=NOW - timedelta(hours=5), concluido=False
    )

    candidatas = await repository.list_inactive(
        before=NOW - timedelta(minutes=30), limit=50
    )

    assert esperando.id not in candidatas


async def test_list_inactive_ignora_sessao_ja_encerrada(
    db_session: AsyncSession, aluno_isolado: tuple[Student, Session]
) -> None:
    student, _ = aluno_isolado
    repository: SessionRepository = SqlAlchemySessionRepository(db_session)
    fechada = await _sessao_aberta(
        db_session, student.id, aberta_em=NOW - timedelta(hours=4)
    )
    await repository.try_end(fechada.id, NOW - timedelta(hours=1))
    await db_session.commit()

    candidatas = await repository.list_inactive(
        before=NOW - timedelta(minutes=30), limit=50
    )

    assert fechada.id not in candidatas


async def test_list_inactive_devolve_as_mais_antigas_primeiro_e_respeita_o_lote(
    db_session: AsyncSession, aluno_isolado: tuple[Student, Session]
) -> None:
    """Sem ordem, a sessão parada há mais tempo ficaria fora de toda rodada."""
    student, _ = aluno_isolado
    repository: SessionRepository = SqlAlchemySessionRepository(db_session)
    mais_velha = await _sessao_aberta(
        db_session, student.id, aberta_em=NOW - timedelta(hours=10)
    )
    do_meio = await _sessao_aberta(
        db_session, student.id, aberta_em=NOW - timedelta(hours=8)
    )
    await _sessao_aberta(db_session, student.id, aberta_em=NOW - timedelta(hours=6))

    candidatas = await repository.list_inactive(
        before=NOW - timedelta(minutes=30), limit=2
    )

    assert candidatas == [mais_velha.id, do_meio.id]


# --- Auth: credentials, refresh_tokens, email_verification_tokens (CARD-049) -


async def test_credential_faz_roundtrip_por_email_e_por_student_id(
    db_session: AsyncSession, aluno_isolado: tuple[Student, Session]
) -> None:
    student, _sessao = aluno_isolado
    repository: CredentialRepository = SqlAlchemyCredentialRepository(db_session)
    credencial = Credential(
        id=uuid4(),
        student_id=student.id,
        email=f"{student.id}@example.com",
        password_hash="$argon2id$fake$para-teste",
        created_at=NOW,
    )

    await repository.add(credencial)
    await db_session.commit()

    por_email = await repository.get_by_email(credencial.email)
    por_student = await repository.get_by_student_id(student.id)
    assert por_email == credencial
    assert por_student == credencial


async def test_credential_email_duplicado_e_recusado(
    db_session: AsyncSession, aluno_isolado: tuple[Student, Session]
) -> None:
    student, _sessao = aluno_isolado
    outro = Student(id=uuid4(), display_name="Outro aluno", created_at=NOW)
    students: StudentRepository = SqlAlchemyStudentRepository(db_session)
    await students.add(outro)
    await db_session.commit()

    repository: CredentialRepository = SqlAlchemyCredentialRepository(db_session)
    email_compartilhado = f"{student.id}@example.com"
    await repository.add(
        Credential(
            id=uuid4(),
            student_id=student.id,
            email=email_compartilhado,
            password_hash="hash-1",
            created_at=NOW,
        )
    )
    await db_session.commit()

    await repository.add(
        Credential(
            id=uuid4(),
            student_id=outro.id,
            email=email_compartilhado,
            password_hash="hash-2",
            created_at=NOW,
        )
    )
    uow: UnitOfWork = SqlAlchemyUnitOfWork(db_session)
    with pytest.raises(ConflictingWriteError):
        await uow.commit()


async def test_mark_email_verified_persiste(
    db_session: AsyncSession, aluno_isolado: tuple[Student, Session]
) -> None:
    student, _sessao = aluno_isolado
    repository: CredentialRepository = SqlAlchemyCredentialRepository(db_session)
    credencial = Credential(
        id=uuid4(),
        student_id=student.id,
        email=f"{student.id}@example.com",
        password_hash="hash",
        created_at=NOW,
    )
    await repository.add(credencial)
    await db_session.commit()

    await repository.mark_email_verified(student.id, NOW + timedelta(hours=1))
    await db_session.commit()

    relida = await repository.get_by_student_id(student.id)
    assert relida is not None
    assert relida.is_email_verified is True


async def test_refresh_token_faz_roundtrip_por_hash(
    db_session: AsyncSession, aluno_isolado: tuple[Student, Session]
) -> None:
    student, _sessao = aluno_isolado
    repository: RefreshTokenRepository = SqlAlchemyRefreshTokenRepository(db_session)
    token = RefreshToken(
        id=uuid4(),
        student_id=student.id,
        family_id=uuid4(),
        token_hash=f"hash-{uuid4()}",
        created_at=NOW,
        expires_at=NOW + timedelta(days=30),
    )

    await repository.add(token)
    await db_session.commit()

    relido = await repository.get_by_hash(token.token_hash)
    assert relido == token


async def test_revoke_family_revoga_so_os_vivos_e_preserva_o_instante_anterior(
    db_session: AsyncSession, aluno_isolado: tuple[Student, Session]
) -> None:
    """A invariante central da detecção de reuso (ADR-0007), contra Postgres real."""
    student, _sessao = aluno_isolado
    repository: RefreshTokenRepository = SqlAlchemyRefreshTokenRepository(db_session)
    familia = uuid4()
    ja_revogado = RefreshToken(
        id=uuid4(),
        student_id=student.id,
        family_id=familia,
        token_hash=f"hash-a-{uuid4()}",
        created_at=NOW,
        expires_at=NOW + timedelta(days=30),
        revoked_at=NOW + timedelta(minutes=5),
    )
    vivo = RefreshToken(
        id=uuid4(),
        student_id=student.id,
        family_id=familia,
        token_hash=f"hash-b-{uuid4()}",
        created_at=NOW,
        expires_at=NOW + timedelta(days=30),
    )
    await repository.add(ja_revogado)
    await repository.add(vivo)
    await db_session.commit()

    await repository.revoke_family(familia, NOW + timedelta(hours=1))
    await db_session.commit()

    relido_antigo = await repository.get_by_hash(ja_revogado.token_hash)
    relido_vivo = await repository.get_by_hash(vivo.token_hash)
    assert relido_antigo is not None
    assert relido_antigo.revoked_at == NOW + timedelta(minutes=5)
    assert relido_vivo is not None
    assert relido_vivo.revoked_at == NOW + timedelta(hours=1)


async def test_email_verification_token_faz_roundtrip_e_mark_used(
    db_session: AsyncSession, aluno_isolado: tuple[Student, Session]
) -> None:
    student, _sessao = aluno_isolado
    repository: EmailVerificationTokenRepository = (
        SqlAlchemyEmailVerificationTokenRepository(db_session)
    )
    token = EmailVerificationToken(
        id=uuid4(),
        student_id=student.id,
        token_hash=f"hash-{uuid4()}",
        created_at=NOW,
        expires_at=NOW + timedelta(hours=24),
    )
    await repository.add(token)
    await db_session.commit()

    assert (await repository.get_by_hash(token.token_hash)) == token

    await repository.mark_used(token.id, NOW + timedelta(minutes=10))
    await db_session.commit()

    relido = await repository.get_by_hash(token.token_hash)
    assert relido is not None
    assert relido.used_at == NOW + timedelta(minutes=10)


async def test_password_reset_token_faz_roundtrip_e_mark_used(
    db_session: AsyncSession, aluno_isolado: tuple[Student, Session]
) -> None:
    student, _sessao = aluno_isolado
    repository: PasswordResetTokenRepository = SqlAlchemyPasswordResetTokenRepository(
        db_session
    )
    token = PasswordResetToken(
        id=uuid4(),
        student_id=student.id,
        token_hash=f"hash-{uuid4()}",
        created_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )
    await repository.add(token)
    await db_session.commit()

    assert (await repository.get_by_hash(token.token_hash)) == token

    await repository.mark_used(token.id, NOW + timedelta(minutes=10))
    await db_session.commit()

    relido = await repository.get_by_hash(token.token_hash)
    assert relido is not None
    assert relido.used_at == NOW + timedelta(minutes=10)


async def test_update_password_hash_persiste(
    db_session: AsyncSession, aluno_isolado: tuple[Student, Session]
) -> None:
    student, _sessao = aluno_isolado
    repository: CredentialRepository = SqlAlchemyCredentialRepository(db_session)
    await repository.add(
        Credential(
            id=uuid4(),
            student_id=student.id,
            email=f"{student.id}@example.com",
            password_hash="hash-antigo",
            created_at=NOW,
        )
    )
    await db_session.commit()

    await repository.update_password_hash(student.id, "hash-novo")
    await db_session.commit()

    relida = await repository.get_by_student_id(student.id)
    assert relida is not None
    assert relida.password_hash == "hash-novo"


async def test_revoke_all_for_student_revoga_duas_familias_diferentes(
    db_session: AsyncSession, aluno_isolado: tuple[Student, Session]
) -> None:
    """A invariante de troca de senha: TODAS as sessões, não só uma família."""
    student, _sessao = aluno_isolado
    repository: RefreshTokenRepository = SqlAlchemyRefreshTokenRepository(db_session)
    familia_a = RefreshToken(
        id=uuid4(),
        student_id=student.id,
        family_id=uuid4(),
        token_hash=f"hash-a-{uuid4()}",
        created_at=NOW,
        expires_at=NOW + timedelta(days=30),
    )
    familia_b = RefreshToken(
        id=uuid4(),
        student_id=student.id,
        family_id=uuid4(),
        token_hash=f"hash-b-{uuid4()}",
        created_at=NOW,
        expires_at=NOW + timedelta(days=30),
    )
    await repository.add(familia_a)
    await repository.add(familia_b)
    await db_session.commit()

    await repository.revoke_all_for_student(student.id, NOW + timedelta(minutes=1))
    await db_session.commit()

    relido_a = await repository.get_by_hash(familia_a.token_hash)
    relido_b = await repository.get_by_hash(familia_b.token_hash)
    assert relido_a is not None
    assert relido_a.revoked_at is not None
    assert relido_b is not None
    assert relido_b.revoked_at is not None
