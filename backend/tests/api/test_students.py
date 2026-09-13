"""``GET /v1/students/me/quota`` (CARD-033) e ``DELETE /v1/students/me``
(CARD-051, ADR-0069)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from fastapi import FastAPI
from httpx import AsyncClient

from fakes_api import AGORA, ALUNO, Fakes
from voicecoach.adapters.auth.jwt_access_token_issuer import JwtAccessTokenIssuer
from voicecoach.api import dependencies as deps
from voicecoach.config import Settings
from voicecoach.domain.auth import RefreshToken
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


# -- DELETE /v1/students/me (CARD-051, ADR-0069) -----------------------------


async def test_excluir_conta_marca_e_revoga_devolve_204(
    client: AsyncClient, fakes: Fakes
) -> None:
    token = RefreshToken(
        id=uuid4(),
        student_id=ALUNO,
        family_id=uuid4(),
        token_hash="hash-de-um-refresh-vivo",
        created_at=AGORA,
        expires_at=AGORA + timedelta(days=30),
    )
    fakes.refresh_tokens.by_id[token.id] = token

    resposta = await client.delete("/v1/students/me")

    assert resposta.status_code == 204
    aluno = await fakes.students.get(ALUNO)
    assert aluno is not None
    assert not aluno.is_active
    assert fakes.refresh_tokens.by_id[token.id].revoked_at is not None


async def test_excluir_conta_e_idempotente_segunda_chamada_tambem_204(
    client: AsyncClient, fakes: Fakes
) -> None:
    primeira = await client.delete("/v1/students/me")
    segunda = await client.delete("/v1/students/me")

    assert primeira.status_code == 204
    assert segunda.status_code == 204


async def test_excluir_conta_respeita_o_limite_por_conta(
    client: AsyncClient, fakes: Fakes, settings: Settings
) -> None:
    fakes.rate_limiter.permitido = False

    resposta = await client.delete("/v1/students/me")

    assert resposta.status_code == 429
    assert resposta.json()["type"].endswith(":rate-limited")


async def test_token_ja_emitido_para_de_valer_depois_da_exclusao(
    app: FastAPI, client: AsyncClient, fakes: Fakes, settings: Settings
) -> None:
    """O critério de aceite central do card, ponta a ponta: a exclusão é
    imediata mesmo dentro da janela em que o access token stateless (15 min,
    ADR-0007) continuaria válido no caso comum. Aqui `requesting_student_id`
    roda de VERDADE — sem o override do fixture `app` — para provar que é a
    checagem contra `Student.deleted_at` (ADR-0069), não o override de teste,
    quem bloqueia.
    """
    app.dependency_overrides.pop(deps.requesting_student_id)
    issuer = JwtAccessTokenIssuer(
        secret=settings.jwt_secret, ttl=settings.access_token_ttl
    )
    token = issuer.issue(ALUNO)
    client.headers["Authorization"] = f"Bearer {token}"

    antes = await client.get("/v1/students/me/quota")
    assert antes.status_code == 200

    exclusao = await client.delete("/v1/students/me")
    assert exclusao.status_code == 204

    depois = await client.get("/v1/students/me/quota")
    assert depois.status_code == 401
