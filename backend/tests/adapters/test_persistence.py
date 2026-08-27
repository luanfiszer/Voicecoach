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
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from testcontainers.community.postgres import PostgresContainer

from voicecoach.adapters.persistence.engine import (
    create_engine,
    create_session_factory,
)
from voicecoach.adapters.persistence.mappers import StaleTurnError
from voicecoach.adapters.persistence.repositories import (
    RowNotFoundError,
    SqlAlchemySessionRepository,
    SqlAlchemyStudentRepository,
    SqlAlchemyTurnRepository,
    SqlAlchemyUsageEventRepository,
)
from voicecoach.adapters.persistence.seed import (
    DEV_STUDENT_DISPLAY_NAME,
    DEV_STUDENT_ID,
)
from voicecoach.adapters.persistence.unit_of_work import SqlAlchemyUnitOfWork
from voicecoach.application.ports.repositories import (
    ConflictingWriteError,
    SessionRepository,
    StudentRepository,
    TurnRepository,
    UnitOfWork,
    UsageEventRepository,
)
from voicecoach.domain.correction import Correction, CorrectionType, Severity
from voicecoach.domain.session import Session
from voicecoach.domain.student import Student
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
