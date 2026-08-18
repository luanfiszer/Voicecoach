"""Fixtures compartilhadas.

`conftest.py` é o arquivo que o pytest carrega automaticamente para o diretório
e seus subdiretórios — as fixtures declaradas aqui ficam visíveis nos testes sem
nenhum import. Não há paralelo direto em xUnit; o mais próximo seria uma
`ClassFixture`/`CollectionFixture` que o runner injetasse por convenção.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from voicecoach.api.app import create_app
from voicecoach.config import Settings


@pytest.fixture
def settings() -> Settings:
    """Configuração de teste, isolada do ambiente da máquina.

    `_env_file=None` desliga a leitura do `.env`: sem isso, um `.env` real na
    máquina do desenvolvedor mudaria o resultado do teste — e o teste passaria
    aqui para falhar no CI.
    """
    return Settings(anthropic_api_key="test-key", _env_file=None)  # type: ignore[call-arg]


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Client HTTP que fala com o app em memória, sem abrir porta.

    `ASGITransport` chama a aplicação ASGI direto, no mesmo processo — o
    equivalente do `WebApplicationFactory`/`TestServer` do ASP.NET Core. O
    `async with` é um context manager assíncrono: garante o fechamento do client
    mesmo se o teste falhar (≈ `await using`).
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
