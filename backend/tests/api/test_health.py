"""Testes dos endpoints de saúde (CARD-002).

Não sobem container: os checks reais são substituídos por
`app.dependency_overrides`. Teste contra Postgres/Redis/MinIO de verdade é
integração de adapter e entra com testcontainers no CARD-003.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import ValidationError

from voicecoach.adapters.health import DependencyStatus
from voicecoach.api.dependencies import check_dependencies
from voicecoach.config import Settings


def _override(app: FastAPI, statuses: list[DependencyStatus]) -> None:
    async def _fake() -> list[DependencyStatus]:
        return statuses

    app.dependency_overrides[check_dependencies] = _fake


async def test_liveness_responde_sem_tocar_em_dependencia(client: AsyncClient) -> None:
    # Nenhum override: se o liveness falasse com a infraestrutura, este teste
    # tentaria abrir conexão de verdade e falharia (ou ficaria lento).
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


async def test_readiness_200_quando_as_tres_dependencias_respondem(
    app: FastAPI, client: AsyncClient
) -> None:
    _override(
        app,
        [
            DependencyStatus("postgres", up=True, latency_ms=3),
            DependencyStatus("redis", up=True, latency_ms=1),
            DependencyStatus("minio", up=True, latency_ms=5),
        ],
    )

    response = await client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert set(body["checks"]) == {"postgres", "redis", "minio"}
    assert all(check["status"] == "up" for check in body["checks"].values())


async def test_readiness_503_e_nomeia_quem_caiu(app: FastAPI, client: AsyncClient) -> None:
    _override(
        app,
        [
            DependencyStatus("postgres", up=True, latency_ms=3),
            DependencyStatus("redis", up=False, latency_ms=2000, error="timeout after 2s"),
            DependencyStatus("minio", up=True, latency_ms=5),
        ],
    )

    response = await client.get("/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["redis"] == {
        "status": "down",
        "latency_ms": 2000,
        "error": "timeout after 2s",
    }
    # O payload do 503 continua completo: quem depura precisa do quadro inteiro.
    assert body["checks"]["postgres"]["status"] == "up"


def test_configuracao_recusa_boot_sem_anthropic_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Critério de aceite do CARD-002: falta a chave, a aplicação não sobe.

    `monkeypatch.delenv` remove a variável só durante este teste — o pytest
    desfaz depois, sem contaminar os outros.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)  # type: ignore[call-arg]

    message = str(exc_info.value)
    assert "anthropic_api_key" in message.lower()
    assert "required" in message.lower()
