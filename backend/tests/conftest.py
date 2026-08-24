"""Fixtures compartilhadas.

`conftest.py` é o arquivo que o pytest carrega automaticamente para o diretório
e seus subdiretórios — as fixtures declaradas aqui ficam visíveis nos testes sem
nenhum import. Não há paralelo direto em xUnit; o mais próximo seria uma
`ClassFixture`/`CollectionFixture` que o runner injetasse por convenção.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from fakes_api import AGORA, TURN_ID, Fakes
from voicecoach.api import dependencies as deps
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
def fakes() -> Fakes:
    """Os dublês das portas da borda (ver `tests/api/fakes_api.py`)."""
    return Fakes()


@pytest.fixture
def app(settings: Settings, fakes: Fakes) -> Iterator[FastAPI]:
    """O app real, com as PORTAS trocadas por dublês.

    O grafo de dependências é exatamente o do processo de produção — o que muda
    é a folha: cada provider de porta de `api/dependencies.py` é substituído por
    `app.dependency_overrides`. É por isso que nenhum teste de rota sobe
    Postgres, Redis ou MinIO, e o `lifespan` (que abriria os pools) nem chega a
    rodar, porque o `ASGITransport` do httpx não dispara eventos de ciclo de vida.

    É aqui que `Protocol` se paga: um dublê é uma classe com os métodos certos,
    sem framework de mock e sem registro. E quem verifica que ele **serve** é o
    `mypy` — foi o que reprovou dois dublês nesta sessão, no instante em que
    `TurnRepository` ganhou `get_by_idempotency_key` e `TurnEvents` ganhou
    `subscribe`, com o `pytest` ainda verde.
    """
    aplicacao = create_app(settings)
    aplicacao.dependency_overrides.update(
        {
            deps.turn_repository: lambda: fakes.turns,
            deps.session_repository: lambda: fakes.sessions,
            deps.unit_of_work: lambda: fakes.uow,
            deps.media_storage: lambda: fakes.storage,
            deps.turn_queue: lambda: fakes,
            deps.turn_events: lambda: fakes.canal,
            deps.agora: lambda: AGORA,
            deps.novo_turn_id: lambda: TURN_ID,
        }
    )
    yield aplicacao
    aplicacao.dependency_overrides.clear()


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
