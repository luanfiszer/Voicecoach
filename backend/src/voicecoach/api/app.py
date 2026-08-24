"""Composition root da API: monta o FastAPI com a configuração validada.

Subir em desenvolvimento::

    uv run uvicorn voicecoach.api.app:create_app --factory --reload

``--factory`` faz o uvicorn chamar ``create_app()`` em vez de procurar uma
variável ``app`` pronta no módulo. É o que mantém o fail-fast no lugar certo:
a configuração é validada quando o servidor sobe, e não quando alguém
simplesmente importa este módulo.
"""

from __future__ import annotations

from fastapi import FastAPI

from voicecoach.api.errors import register_exception_handlers
from voicecoach.api.lifespan import lifespan
from voicecoach.api.routes import health, v1
from voicecoach.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Constrói a aplicação.

    Sem argumento, lê a configuração do ambiente e **falha aqui** se faltar
    variável obrigatória — antes de qualquer requisição. Com argumento, aceita
    uma configuração já pronta: é assim que o teste roda sem depender do
    ``.env`` da máquina.
    """
    resolved = settings if settings is not None else get_settings()

    app = FastAPI(
        title="Voicecoach API",
        version="0.1.0",
        summary="Professor de inglês por conversa de áudio.",
        # O `lifespan` abre os pools do processo (engine, arq, redis, S3) e os
        # fecha ao descer. Ele NÃO roda quando o app é exercido pelo
        # `ASGITransport` do httpx — que é justamente o que permite ao teste de
        # rota substituir as portas por fakes sem subir infraestrutura nenhuma.
        lifespan=lifespan,
    )
    # `app.state` é o saco de estado do processo que o FastAPI oferece; as
    # dependências leem a configuração dali via `Request`, em vez de importar
    # um singleton global (que amarraria os testes ao ambiente).
    app.state.settings = resolved

    # A tradução de erro do núcleo para HTTP, num lugar só — a borda que o
    # ADR-0017 prometeu e que só existiu a partir do CARD-010.
    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(v1)
    return app
