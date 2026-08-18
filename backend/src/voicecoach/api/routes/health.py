"""Endpoints de saúde: liveness e readiness (ADR-0014).

A distinção não é cosmética:

- ``GET /health`` (liveness) responde "o processo está vivo". **Não toca em
  dependência nenhuma** — se ele falhasse porque o Postgres caiu, um
  supervisor mataria uma API perfeitamente sadia por causa de um vizinho.
- ``GET /health/ready`` (readiness) responde "posso receber tráfego", e para
  isso precisa checar quem eu preciso para trabalhar.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from voicecoach.adapters.health import DependencyStatus
from voicecoach.api.dependencies import check_dependencies
from voicecoach.api.schemas.health import (
    DependencyCheck,
    LivenessResponse,
    ReadinessResponse,
)

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness — o processo responde")
async def liveness() -> LivenessResponse:
    return LivenessResponse()


@router.get(
    "/health/ready",
    summary="Readiness — as dependências de infraestrutura respondem",
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ReadinessResponse,
            "description": "Alguma dependência está fora; o payload diz qual.",
        }
    },
)
async def readiness(
    statuses: Annotated[list[DependencyStatus], Depends(check_dependencies)],
    response: Response,
) -> ReadinessResponse:
    """200 apenas se as três dependências responderem; 503 caso contrário.

    O corpo é o mesmo nos dois casos — quem depura precisa saber *qual* caiu, e
    isso não deve depender de o endpoint ter respondido 200.
    """
    ready = all(dependency.up for dependency in statuses)
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        status="ready" if ready else "not_ready",
        checks={
            dependency.name: DependencyCheck(
                status="up" if dependency.up else "down",
                latency_ms=dependency.latency_ms,
                error=dependency.error,
            )
            for dependency in statuses
        },
    )
