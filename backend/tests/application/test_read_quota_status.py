"""``ReadQuotaStatusHandler``: a mesma regra do freio, do lado da leitura (CARD-033).

Os dois lados (`StartTurnHandler` e este) consultam as MESMAS duas portas
(`UsageEventRepository.totals_for_student`, `ServiceBudget.is_exceeded`) —
`tests/application/test_start_turn_quotas.py` testa o freio; este arquivo
testa que a leitura nunca recusa e informa o motivo certo (RF3/RF4/RF5).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from fakes_pipeline import FakeServiceBudget, FakeUsageEventRepository, RelogioFalso
from voicecoach.application.use_cases.read_quota_status import (
    BlockedReason,
    ReadQuotaStatus,
    ReadQuotaStatusHandler,
)
from voicecoach.domain.usage import UsageEvent

ALUNO = UUID("00000000-0000-0000-0000-000000000001")
# Mesmo instante-âncora do `test_start_turn_quotas.py`: meio-dia UTC de
# 2026-08-23 é 09:00 em America/Sao_Paulo, longe da virada.
AGORA_UTC = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
INICIO_DO_DIA_EM_SP_UTC = datetime(2026, 8, 23, 3, 0, tzinfo=UTC)


def evento(*, spoken: timedelta = timedelta(seconds=30)) -> UsageEvent:
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
    usage_events: FakeUsageEventRepository | None = None,
    budget: FakeServiceBudget | None = None,
    daily_quota_turns: int = 60,
    daily_quota_spoken: timedelta = timedelta(minutes=10),
) -> ReadQuotaStatusHandler:
    return ReadQuotaStatusHandler(
        usage_events=usage_events or FakeUsageEventRepository(),
        service_budget=budget or FakeServiceBudget(),
        clock=RelogioFalso(inicio=AGORA_UTC),
        daily_quota_spoken=daily_quota_spoken,
        daily_quota_turns=daily_quota_turns,
    )


async def test_aluno_sem_consumo_pode_falar_e_a_virada_e_a_meia_noite_de_sp() -> None:
    handler = montar()

    status = await handler.handle(ReadQuotaStatus(student_id=ALUNO))

    assert status.spoken == timedelta(0)
    assert status.quota_spoken == timedelta(minutes=10)
    assert status.resets_at == INICIO_DO_DIA_EM_SP_UTC + timedelta(days=1)
    assert status.service_available is True
    assert status.blocked_reason is None


async def test_minutos_estourados_e_o_motivo_e_daily_minutes() -> None:
    usage = FakeUsageEventRepository()
    await usage.add(evento(spoken=timedelta(minutes=10)))
    handler = montar(usage_events=usage, daily_quota_spoken=timedelta(minutes=10))

    status = await handler.handle(ReadQuotaStatus(student_id=ALUNO))

    assert status.spoken == timedelta(minutes=10)
    assert status.blocked_reason is BlockedReason.DAILY_MINUTES


async def test_teto_de_turns_batido_com_minutos_sobrando_nao_mente_sobre_minutos() -> (
    None
):
    """RF5: o caso esquisito — a barra de minutos continua correta, e o motivo
    do bloqueio é o teto de turns, não "acabaram seus minutos".
    """
    usage = FakeUsageEventRepository()
    for _ in range(2):
        await usage.add(evento(spoken=timedelta(seconds=10)))
    handler = montar(
        usage_events=usage,
        daily_quota_turns=2,
        daily_quota_spoken=timedelta(minutes=10),
    )

    status = await handler.handle(ReadQuotaStatus(student_id=ALUNO))

    assert status.spoken == timedelta(seconds=20)  # bem abaixo do teto de minutos
    assert status.blocked_reason is BlockedReason.MANY_SHORT_TURNS


async def test_kill_switch_ativo_responde_sem_recusar_e_sem_expor_orcamento() -> None:
    handler = montar(budget=FakeServiceBudget(excedido=True))

    status = await handler.handle(ReadQuotaStatus(student_id=ALUNO))

    assert status.service_available is False
    assert status.blocked_reason is BlockedReason.SERVICE_PAUSED
    # Nenhum campo de dinheiro no valor devolvido — só os fatos que a API expõe.
    assert not hasattr(status, "budget_usd")


async def test_kill_switch_vence_o_teto_de_turns_quando_os_dois_mordem() -> None:
    """O serviço pausado é um fato do PRODUTO — prevalece sobre a mecânica do aluno."""
    usage = FakeUsageEventRepository()
    for _ in range(5):
        await usage.add(evento(spoken=timedelta(seconds=1)))
    handler = montar(
        usage_events=usage,
        budget=FakeServiceBudget(excedido=True),
        daily_quota_turns=1,
    )

    status = await handler.handle(ReadQuotaStatus(student_id=ALUNO))

    assert status.blocked_reason is BlockedReason.SERVICE_PAUSED
