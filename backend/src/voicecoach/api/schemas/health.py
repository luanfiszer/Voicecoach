"""Contrato HTTP dos endpoints de saúde."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LivenessResponse(BaseModel):
    """Resposta de ``GET /health``."""

    status: Literal["alive"] = "alive"


class DependencyCheck(BaseModel):
    """Estado de uma dependência de infraestrutura."""

    status: Literal["up", "down"]
    latency_ms: int
    error: str | None = None


class ReadinessResponse(BaseModel):
    """Resposta de ``GET /health/ready``.

    ``status`` é redundante em relação a ``checks`` de propósito: quem faz
    probe lê só o código HTTP, quem depura lê o mapa inteiro.
    """

    status: Literal["ready", "not_ready"]
    checks: dict[str, DependencyCheck] = Field(default_factory=dict)
