"""Providers de dependência do FastAPI — a composição da camada de API.

`Depends` é o container de injeção do FastAPI. O que faz dele diferente de um
`IServiceCollection` é que o "registro" é a própria função: o parâmetro declara
`Depends(check_dependencies)` e o FastAPI chama aquela função. A substituição em
teste é feita por `app.dependency_overrides[funcao] = fake`, que é o mais perto
que se chega de trocar o registro do container num teste de integração.
"""

from __future__ import annotations

import asyncio

from fastapi import Request

from voicecoach.adapters.health import (
    DependencyStatus,
    check_minio,
    check_postgres,
    check_redis,
    check_worker,
)
from voicecoach.config import Settings


def get_settings_from_app(request: Request) -> Settings:
    """A configuração validada no boot, guardada em ``app.state``."""
    settings: Settings = request.app.state.settings
    return settings


async def check_dependencies(request: Request) -> list[DependencyStatus]:
    """Checa as quatro dependências em paralelo.

    A quarta entrou no CARD-009 (ADR-0025, item 4) e é diferente das outras: ela
    não pergunta se um serviço responde, e sim se **existe worker pronto**. Um
    turn aceito sem worker capaz fica na fila até alguém subir.

    `asyncio.gather` dispara as corrotinas juntas e espera todas — é o
    `Task.WhenAll` do C#. Serializar os checks somaria as latências (e, no pior
    caso, os três timeouts) no tempo de resposta do endpoint.
    """
    settings = get_settings_from_app(request)
    return list(
        await asyncio.gather(
            check_postgres(settings.database_url),
            check_redis(settings.redis_url),
            check_minio(settings),
            check_worker(settings.redis_url),
        )
    )
