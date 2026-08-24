"""O caso de uso do POST: idempotência, ordem das escritas e o ``Result``.

Nenhuma infraestrutura: os fakes de ``tests/fakes_pipeline.py`` fazem o papel das
cinco portas, e o teste roda em milissegundos.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from fakes_pipeline import (
    FakeMediaStorage,
    FakeSessionRepository,
    FakeTurnRepository,
    FakeUnitOfWork,
    RelogioFalso,
)
from voicecoach.application.ports.repositories import ConflictingWriteError
from voicecoach.application.ports.turn_queue import TurnQueueError
from voicecoach.application.result import Err, Ok
from voicecoach.application.use_cases.start_turn import (
    SessionNotFound,
    StartTurn,
    StartTurnHandler,
    TurnAccepted,
)
from voicecoach.domain.errors import InvalidStateTransitionError
from voicecoach.domain.session import Session
from voicecoach.domain.turn import Turn

ALUNO = UUID("00000000-0000-0000-0000-000000000001")
AUDIO = b"\x00" * 100
CHAVE = "chave-de-idempotencia-1"


class FilaFalsa:
    def __init__(self, *, erro: Exception | None = None) -> None:
        self.enfileirados: list[UUID] = []
        self._erro = erro

    async def enqueue(self, turn_id: UUID) -> None:
        if self._erro is not None:
            raise self._erro
        self.enfileirados.append(turn_id)


class UnitOfWorkQueColide(FakeUnitOfWork):
    """No primeiro commit: outra requisição já gravou a mesma chave, e nós somos
    recusados pelo índice único.

    O fake **também desfaz o que nós escrevemos**, e isso não é firula: é o que
    um ``ROLLBACK`` faz, e sem ele o teste passaria por um motivo falso — nosso
    turn continuaria visível no repositório e a reconsulta o encontraria em vez
    de encontrar o vencedor.
    """

    def __init__(self, turns: FakeTurnRepository, vencedor: Turn) -> None:
        super().__init__()
        self._turns = turns
        self._vencedor = vencedor
        self.colidiu = False

    async def commit(self) -> None:
        if not self.colidiu:
            self.colidiu = True
            # O vencedor comitou primeiro; o nosso INSERT é desfeito.
            self._turns.turns = {self._vencedor.id: self._vencedor}
            message = "duplicate key value violates unique constraint"
            raise ConflictingWriteError(message)
        await super().commit()


def montar(
    *,
    sessions: FakeSessionRepository,
    turns: FakeTurnRepository | None = None,
    fila: FilaFalsa | None = None,
    storage: FakeMediaStorage | None = None,
    uow: FakeUnitOfWork | None = None,
    turn_id: UUID | None = None,
) -> tuple[StartTurnHandler, FakeTurnRepository, FilaFalsa, FakeMediaStorage]:
    turns = turns or FakeTurnRepository()
    fila = fila or FilaFalsa()
    storage = storage or FakeMediaStorage()
    handler = StartTurnHandler(
        turns=turns,
        sessions=sessions,
        unit_of_work=uow or FakeUnitOfWork(),
        storage=storage,
        queue=fila,
        clock=RelogioFalso(),
        new_turn_id=lambda: turn_id or UUID("11111111-1111-1111-1111-111111111111"),
    )
    return handler, turns, fila, storage


def sessao_ativa() -> Session:
    return Session(
        id=uuid4(), student_id=ALUNO, started_at=datetime(2026, 8, 23, tzinfo=UTC)
    )


def comando(session_id: UUID, *, key: str = CHAVE) -> StartTurn:
    return StartTurn(
        session_id=session_id,
        idempotency_key=key,
        audio=AUDIO,
        content_type="audio/aac",
        extension="aac",
        audio_duration=timedelta(seconds=4),
    )


async def test_aceita_o_turn_grava_o_audio_e_enfileira() -> None:
    session = sessao_ativa()
    handler, turns, fila, storage = montar(sessions=FakeSessionRepository(session))

    resultado = await handler.handle(comando(session.id))

    assert isinstance(resultado, Ok)
    aceito: TurnAccepted = resultado.value
    assert aceito.replayed is False

    turn = turns.turns[aceito.turn_id]
    assert turn.idempotency_key == CHAVE
    assert turn.audio_duration == timedelta(seconds=4)
    # A chave segue o esquema do ADR-0024 — e é a MESMA que foi ao storage.
    assert turn.input_audio_ref == f"{ALUNO}/{session.id}/{turn.id}/input.aac"
    assert storage.objetos[turn.input_audio_ref] == (AUDIO, "audio/aac")
    assert fila.enfileirados == [turn.id]


async def test_o_audio_sobe_antes_de_o_turn_existir_no_repositorio() -> None:
    """Ordem invertida deixa o cliente com uma linha apontando para um 404.

    O inverso — objeto sem linha — é lixo que a retenção de 7 dias recolhe
    (ADR-0024). Por isso a ordem é storage → banco, a mesma do worker.
    """
    session = sessao_ativa()
    storage = FakeMediaStorage(falhar_em=RuntimeError("storage fora"))
    handler, turns, fila, _ = montar(
        sessions=FakeSessionRepository(session), storage=storage
    )

    with pytest.raises(RuntimeError):
        await handler.handle(comando(session.id))

    assert turns.turns == {}
    assert fila.enfileirados == []


async def test_a_mesma_chave_devolve_o_mesmo_turn_e_nao_cria_outro() -> None:
    """O critério de aceite central da idempotência (CARD-010)."""
    session = sessao_ativa()
    handler, turns, _fila, storage = montar(sessions=FakeSessionRepository(session))

    primeiro = await handler.handle(comando(session.id))
    segundo = await handler.handle(comando(session.id))

    assert isinstance(primeiro, Ok)
    assert isinstance(segundo, Ok)
    assert segundo.value.turn_id == primeiro.value.turn_id
    assert segundo.value.replayed is True
    # UM turn no banco, e UM objeto no storage.
    assert len(turns.turns) == 1
    assert len(storage.objetos) == 1


async def test_o_reenvio_enfileira_de_novo_e_cura_o_crash_entre_gravar_e_publicar() -> (
    None
):
    """Estado de crash 2: Turn gravado, job nunca publicado.

    O retry natural do cliente conserta, porque o caminho repetido também
    enfileira — e o ``_job_id`` do ``ArqTurnQueue`` impede que isso vire dois
    jobs (é contrato do adapter, verificado lá).
    """
    session = sessao_ativa()
    handler, _, fila, _ = montar(sessions=FakeSessionRepository(session))

    await handler.handle(comando(session.id))
    await handler.handle(comando(session.id))

    assert len(fila.enfileirados) == 2
    assert len(set(fila.enfileirados)) == 1


async def test_perder_a_corrida_pela_chave_devolve_o_turn_de_quem_chegou_antes() -> (
    None
):
    """A consulta é uma foto; o índice único é a lei.

    Sem esta tradução, um duplo toque no botão viraria 500 — o caso mais banal
    que a idempotência existe para tratar.
    """
    session = sessao_ativa()
    vencedor_id = UUID("99999999-9999-9999-9999-999999999999")
    vencedor = session.start_turn(
        turn_id=vencedor_id,
        input_audio_ref="outro",
        audio_duration=timedelta(seconds=1),
        now=datetime(2026, 8, 23, tzinfo=UTC),
        idempotency_key=CHAVE,
    )
    turns = FakeTurnRepository()
    handler, turns, fila, _ = montar(
        sessions=FakeSessionRepository(session),
        turns=turns,
        uow=UnitOfWorkQueColide(turns, vencedor),
    )

    resultado = await handler.handle(comando(session.id))

    assert isinstance(resultado, Ok)
    assert resultado.value.turn_id == vencedor_id
    assert resultado.value.replayed is True
    assert fila.enfileirados == [vencedor_id]


async def test_sessao_inexistente_e_err_e_nao_excecao() -> None:
    """A decisão do ``Result``: id de sessão velho é entrada do mundo, não bug.

    O cliente guarda o id no aparelho; o banco pode ter sido recriado em
    desenvolvimento. Não há invariante violada — há um recurso que não existe.
    """
    handler, _turns, fila, storage = montar(sessions=FakeSessionRepository())

    resultado = await handler.handle(comando(uuid4()))

    assert isinstance(resultado, Err)
    assert isinstance(resultado.error, SessionNotFound)
    # E nada aconteceu: nem objeto no storage, nem job.
    assert storage.objetos == {}
    assert fila.enfileirados == []


async def test_sessao_encerrada_levanta_porque_e_invariante_do_agregado() -> None:
    """O outro lado da fronteira do ADR-0017, no mesmo caso de uso.

    ``Session.start_turn`` recusa porque só quem conhece o próprio estado pode
    decidir se aceita mais um turno. Isso é invariante, não desfecho — e é a
    borda que traduz para 409.
    """
    session = sessao_ativa()
    session.end(datetime(2026, 8, 23, 23, 0, tzinfo=UTC))
    handler, _, fila, _ = montar(sessions=FakeSessionRepository(session))

    with pytest.raises(InvalidStateTransitionError):
        await handler.handle(comando(session.id))

    assert fila.enfileirados == []


async def test_fila_fora_do_ar_atravessa_como_erro_de_porta() -> None:
    """503 na borda: o turn está gravado, mas ninguém foi avisado.

    Não é ``Err``: infraestrutura caída não é desfecho do negócio, e o cliente
    deve tentar de novo — com a mesma chave, que agora encontra o turn.
    """
    session = sessao_ativa()
    fila = FilaFalsa(erro=TurnQueueError("redis fora"))
    handler, turns, _, _ = montar(sessions=FakeSessionRepository(session), fila=fila)

    with pytest.raises(TurnQueueError):
        await handler.handle(comando(session.id))

    # O turn EXISTE: foi gravado antes de enfileirar. É o estado de crash 2, e
    # é o CARD-025 (ou o retry do cliente) quem o resolve.
    assert len(turns.turns) == 1
