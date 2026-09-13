"""``GET /v1/students/me/quota`` — o saldo como leitura (CARD-033)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from httpx import AsyncClient

from fakes_api import AGORA, ALUNO, Fakes
from voicecoach.config import Settings
from voicecoach.domain.usage import UsageEvent


def evento_de_hoje(*, spoken: timedelta = timedelta(seconds=30)) -> UsageEvent:
    return UsageEvent(
        turn_id=uuid4(),
        student_id=ALUNO,
        occurred_at=AGORA,
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


async def test_sem_consumo_devolve_zero_e_pode_falar(
    client: AsyncClient, fakes: Fakes
) -> None:
    resposta = await client.get("/v1/students/me/quota")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["spoken_seconds"] == 0.0
    assert corpo["service_available"] is True
    assert corpo["blocked_reason"] is None


async def test_kill_switch_ativo_responde_200_sem_expor_orcamento(
    client: AsyncClient, fakes: Fakes
) -> None:
    fakes.budget.excedido = True

    resposta = await client.get("/v1/students/me/quota")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["service_available"] is False
    assert corpo["blocked_reason"] == "service_paused"
    assert "budget_usd" not in corpo
    assert "orcamento" not in corpo


async def test_cota_diaria_estourada_e_o_motivo_e_daily_minutes(
    client: AsyncClient, fakes: Fakes, settings: Settings
) -> None:
    fakes.usage_events.eventos[uuid4()] = evento_de_hoje(
        spoken=timedelta(minutes=settings.daily_audio_minutes_per_student)
    )

    resposta = await client.get("/v1/students/me/quota")

    corpo = resposta.json()
    assert corpo["blocked_reason"] == "daily_minutes"


async def test_a_mesma_leitura_que_o_post_de_turn_usa(
    client: AsyncClient, fakes: Fakes
) -> None:
    """RNF3: mesma fonte que o freio — o saldo bate com o que o POST veria."""
    fakes.usage_events.eventos[uuid4()] = evento_de_hoje(spoken=timedelta(minutes=3))

    resposta = await client.get("/v1/students/me/quota")

    assert resposta.json()["spoken_seconds"] == 180.0
