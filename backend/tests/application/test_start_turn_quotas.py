"""Cota diária e kill switch dentro do `StartTurnHandler` (ADR-0063, CARD-015).

Os testes de atomicidade de verdade (corrida entre requisições concorrentes)
moram em `tests/adapters/test_quota_redis.py`, contra Redis real — aqui o que
se verifica é a REGRA: qual desfecho, em que ordem, e que nada é criado quando
a resposta é recusar.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from fakes_pipeline import (
    FakeMediaStorage,
    FakeServiceBudget,
    FakeSessionRepository,
    FakeTurnRepository,
    FakeUnitOfWork,
    FakeUsageEventRepository,
    RelogioFalso,
)
from voicecoach.application.result import Err, Ok
from voicecoach.application.use_cases.start_turn import (
    DailyQuotaExceeded,
    ServiceBudgetExceeded,
    StartTurn,
    StartTurnHandler,
)
from voicecoach.domain.session import Session
from voicecoach.domain.usage import UsageEvent

ALUNO = UUID("00000000-0000-0000-0000-000000000001")
AUDIO = b"\x00" * 100
# Meio-dia UTC de 2026-08-23 é 09:00 em America/Sao_Paulo (UTC-3, sem
# horário de verão desde 2019) — bem longe da meia-noite, para os testes de
# janela não dependerem de aritmética de fuso para o instante "agora".
AGORA_UTC = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
INICIO_DO_DIA_EM_SP_UTC = datetime(2026, 8, 23, 3, 0, tzinfo=UTC)


class FilaFalsa:
    def __init__(self) -> None:
        self.enfileirados: list[UUID] = []

    async def enqueue(self, turn_id: UUID) -> None:
        self.enfileirados.append(turn_id)


def sessao_ativa() -> Session:
    return Session(id=uuid4(), student_id=ALUNO, started_at=AGORA_UTC)


def comando(session_id: UUID, *, key: str = "chave-1") -> StartTurn:
    return StartTurn(
        session_id=session_id,
        idempotency_key=key,
        audio=AUDIO,
        content_type="audio/aac",
        extension="aac",
        audio_duration=timedelta(seconds=4),
    )


def evento_de_hoje(*, spoken: timedelta = timedelta(seconds=30)) -> UsageEvent:
    """Um `UsageEvent` do ALUNO, ocorrido bem dentro da janela de hoje."""
    return UsageEvent(
        turn_id=uuid4(),
        student_id=ALUNO,
        occurred_at=AGORA_UTC,
        llm_model="claude-haiku-4-5-20251001",
        llm_input_tokens=100,
        llm_cache_creation_tokens=0,
        llm_cache_read_tokens=0,
        llm_output_tokens=50,
        stt_audio_duration=spoken,
        stt_provider="faster_whisper",
        stt_confidence=-0.1,
        stt_no_speech=0.0,
        tts_chars=80,
        tts_provider="piper",
        estimated_cost_usd=Decimal("0.001"),
    )


def montar(
    *,
    session: Session,
    usage_events: FakeUsageEventRepository,
    turns: FakeTurnRepository | None = None,
    fila: FilaFalsa | None = None,
    budget: FakeServiceBudget | None = None,
    daily_quota_turns: int = 60,
    daily_quota_spoken: timedelta = timedelta(minutes=10),
) -> tuple[StartTurnHandler, FakeTurnRepository, FilaFalsa, FakeMediaStorage]:
    turns = turns or FakeTurnRepository()
    fila = fila or FilaFalsa()
    storage = FakeMediaStorage()
    handler = StartTurnHandler(
        turns=turns,
        sessions=FakeSessionRepository(session),
        usage_events=usage_events,
        unit_of_work=FakeUnitOfWork(),
        storage=storage,
        queue=fila,
        service_budget=budget or FakeServiceBudget(),
        clock=RelogioFalso(inicio=AGORA_UTC),
        new_turn_id=lambda: UUID("11111111-1111-1111-1111-111111111111"),
        daily_quota_turns=daily_quota_turns,
        daily_quota_spoken=daily_quota_spoken,
    )
    return handler, turns, fila, storage


async def test_cota_de_turns_excedida_recusa_sem_criar_nada() -> None:
    session = sessao_ativa()
    usage = FakeUsageEventRepository()
    for _ in range(2):
        await usage.add(evento_de_hoje())
    handler, turns, fila, storage = montar(
        session=session, usage_events=usage, daily_quota_turns=2
    )

    resultado = await handler.handle(comando(session.id))

    assert isinstance(resultado, Err)
    assert isinstance(resultado.error, DailyQuotaExceeded)
    assert resultado.error.reset_at == INICIO_DO_DIA_EM_SP_UTC + timedelta(days=1)
    assert turns.turns == {}
    assert storage.objetos == {}
    assert fila.enfileirados == []


async def test_cota_de_minutos_excedida_recusa_sem_criar_nada() -> None:
    session = sessao_ativa()
    usage = FakeUsageEventRepository()
    await usage.add(evento_de_hoje(spoken=timedelta(minutes=10)))
    handler, turns, fila, storage = montar(
        session=session,
        usage_events=usage,
        daily_quota_spoken=timedelta(minutes=10),
    )

    resultado = await handler.handle(comando(session.id))

    assert isinstance(resultado, Err)
    assert isinstance(resultado.error, DailyQuotaExceeded)
    assert turns.turns == {}
    assert storage.objetos == {}
    assert fila.enfileirados == []


async def test_abaixo_dos_dois_tetos_e_aceito_normalmente() -> None:
    session = sessao_ativa()
    usage = FakeUsageEventRepository()
    await usage.add(evento_de_hoje())  # 1 turn, 30s — bem abaixo dos tetos
    handler, turns, fila, _storage = montar(
        session=session,
        usage_events=usage,
        daily_quota_turns=60,
        daily_quota_spoken=timedelta(minutes=10),
    )

    resultado = await handler.handle(comando(session.id))

    assert isinstance(resultado, Ok)
    assert len(turns.turns) == 1
    assert fila.enfileirados


async def test_kill_switch_recusa_mesmo_com_cota_por_student_livre() -> None:
    """O orçamento é do PRODUTO, independente de o aluno estar dentro da cota."""
    session = sessao_ativa()
    usage = FakeUsageEventRepository()  # aluno não gastou nada hoje
    budget = FakeServiceBudget(excedido=True)
    handler, turns, fila, storage = montar(
        session=session, usage_events=usage, budget=budget
    )

    resultado = await handler.handle(comando(session.id))

    assert isinstance(resultado, Err)
    assert isinstance(resultado.error, ServiceBudgetExceeded)
    assert turns.turns == {}
    assert storage.objetos == {}
    assert fila.enfileirados == []


async def test_reenvio_idempotente_ignora_cota_e_orcamento_estourados() -> None:
    """F11 (CARD-015): reenviar a MESMA chave nunca é bloqueado por cota nova.

    É o mesmo turn que já foi aceito — recusar o reenvio faria um cliente que
    perdeu a resposta (rede) ficar preso, achando que estourou a cota por um
    turn que ele já pagou.
    """
    session = sessao_ativa()
    usage = FakeUsageEventRepository()
    turns = FakeTurnRepository()
    fila = FilaFalsa()
    handler, turns, fila, _storage = montar(
        session=session,
        usage_events=usage,
        turns=turns,
        fila=fila,
        daily_quota_turns=1000,
    )

    primeiro = await handler.handle(comando(session.id, key="mesma-chave"))
    assert isinstance(primeiro, Ok)

    # Mesmo turns/fila, mas agora com o kill switch ligado e a cota apertada
    # ao ponto de recusar qualquer turn NOVO.
    handler_com_kill_switch, _, _, _ = montar(
        session=session,
        usage_events=usage,
        turns=turns,
        fila=fila,
        budget=FakeServiceBudget(excedido=True),
        daily_quota_turns=0,
    )

    segundo = await handler_com_kill_switch.handle(
        comando(session.id, key="mesma-chave")
    )

    assert isinstance(segundo, Ok)
    assert segundo.value.turn_id == primeiro.value.turn_id
    assert segundo.value.replayed is True
