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

from fakes_api import AGORA, ALUNO, TURN_ID, Fakes
from voicecoach.api import dependencies as deps
from voicecoach.api.app import create_app
from voicecoach.config import Settings


@pytest.fixture(autouse=True)
def _jwt_secret_para_testes(monkeypatch: pytest.MonkeyPatch) -> None:
    """``jwt_secret`` é obrigatório (CARD-049), como ``anthropic_api_key`` já
    era — mas, ao contrário dele, dezenas de `Settings(...)` espalhados pelos
    testes de outros cards não o declaram (não tinham por quê, na época).

    **`autouse` em vez de editar cada construção.** Uma variável de ambiente
    entra na precedência do pydantic-settings ANTES do default declarado —
    ver o docstring de `config.py` — então isto cobre todo `Settings(...)`
    do processo de teste sem tocar em nenhum deles. A alternativa (acrescentar
    `jwt_secret="..."` em cada um) espalharia um detalhe de UM card por
    arquivos de oito cards diferentes que não têm nada a ver com auth.
    """
    monkeypatch.setenv(
        "JWT_SECRET",
        "test-jwt-secret-0123456789abcdef",  # gitleaks:allow
    )


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
            # ADR-0063 (CARD-015): permissivos por padrão — os testes de
            # cota/orçamento/rate limit ajustam o fake pego em `fakes`.
            deps.usage_event_repository: lambda: fakes.usage_events,
            deps.service_budget: lambda: fakes.budget,
            deps.rate_limiter: lambda: fakes.rate_limiter,
            deps.translation_repository: lambda: fakes.translations,
            deps.translator: lambda: fakes.translator,
            # CARD-049: ALUNO é quem a maioria das rotas espera encontrar —
            # os testes de auth de verdade (`test_auth.py`) NÃO usam este
            # fixture de rota; eles chamam os handlers direto, com os fakes
            # crus. `credential_repository` vem com ALUNO já verificado
            # (ver `Fakes.__init__`), então `enforce_verified_email` não
            # bloqueia os testes que não são sobre isso.
            deps.requesting_student_id: lambda: ALUNO,
            deps.student_repository: lambda: fakes.students,
            deps.credential_repository: lambda: fakes.credentials,
            deps.social_identity_repository: lambda: fakes.social_identities,
            deps.refresh_token_repository: lambda: fakes.refresh_tokens,
            deps.email_verification_token_repository: lambda: fakes.verification_tokens,
            deps.password_reset_token_repository: lambda: fakes.password_reset_tokens,
            deps.email_sender: lambda: fakes.email_sender,
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
