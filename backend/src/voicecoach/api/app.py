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

from voicecoach.api.routes import health
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
    )
    # `app.state` é o saco de estado do processo que o FastAPI oferece; as
    # dependências leem a configuração dali via `Request`, em vez de importar
    # um singleton global (que amarraria os testes ao ambiente).
    app.state.settings = resolved
    app.include_router(health.router)
    return app
