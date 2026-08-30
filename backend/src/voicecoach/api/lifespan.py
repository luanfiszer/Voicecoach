"""Os recursos que vivem enquanto o processo da API vive.

**Este arquivo é a lacuna estrutural que o CARD-010 fechou.** Até aqui a API só
tinha o health check, e ele abre e fecha um cliente de Redis **por chamada** —
de propósito: é um probe, roda raramente, e uma conexão vazada num endpoint de
probe derruba a API. O caminho quente é o oposto, e copiar aquele padrão para cá
seria o erro clássico: *funciona no teste e derrete em uso*. Um engine de
SQLAlchemy por request esgota o Postgres; uma conexão de Redis por stream SSE
esgota o Redis com dez alunos.

**`lifespan` é um idioma sem paralelo direto em C#, e cabe em três linhas:** é
um *context manager assíncrono* que o FastAPI entra ao subir e sai ao descer —
tudo antes do ``yield`` roda no boot, tudo depois roda no desligamento, e o
``yield`` é a aplicação inteira acontecendo. O mais próximo em .NET é registrar
singletons no ``Program.cs`` e implementar ``IAsyncDisposable`` no host: aqui as
duas metades ficam **no mesmo arquivo, uma embaixo da outra**, o que torna
impossível abrir algo e esquecer de fechar num arquivo distante.

Por que os quatro recursos precisam disto e não podiam ser criados por request:

===================  ==========================================================
``engine``           é o pool de conexões. Um por request abre e fecha uma
                     conexão TCP + handshake por chamada, e esgota o Postgres
``arq``              ``create_pool`` é **async** — não dá para chamá-lo no
                     ``create_app()``, que é síncrono. Só existe lugar aqui
``redis``            o pub/sub do SSE; uma conexão por stream é o modo de falha
                     mais caro deste card
``storage``          o cliente boto3 monta o modelo do serviço a partir de JSON
                     na primeira construção — refazê-lo por request é caro e
                     inútil, já que ele não guarda estado de sessão
===================  ==========================================================
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import redis.asyncio as redis
from arq.connections import RedisSettings, create_pool

from voicecoach.adapters.persistence.engine import (
    create_engine,
    create_session_factory,
)
from voicecoach.adapters.storage.s3_media_storage import create_media_storage

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from fastapi import FastAPI

    from voicecoach.config import Settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Abre os pools do processo, serve, e os fecha na ordem inversa."""
    settings: Settings = app.state.settings

    engine = create_engine(settings.database_url)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)

    # `create_pool` é async porque negocia a conexão na criação — é a razão
    # técnica de este arquivo existir: ele não cabe num `create_app()` síncrono.
    app.state.arq = await create_pool(RedisSettings.from_dsn(settings.redis_url))

    # Conexão SEPARADA do pool do arq, e não a mesma. Uma conexão em modo
    # `SUBSCRIBE` não aceita mais nenhum outro comando enquanto estiver ouvindo;
    # compartilhá-la com quem enfileira jobs travaria o POST no primeiro stream
    # aberto.
    #
    # **`socket_connect_timeout` sim, `socket_timeout` NÃO** (CARD-026). Os dois
    # parecem irmãos e um deles é armadilha: `socket_timeout` é o prazo de
    # QUALQUER leitura do socket, e o `listen()` do pub/sub fica bloqueado à
    # espera da próxima mensagem por tempo indeterminado — que é o
    # comportamento correto, não uma falha. Configurá-lo derrubaria todo stream
    # SSE ocioso com um `TimeoutError`, e o sintoma apareceria como
    # "reconexões misteriosas" só nas sessões em que o aluno pensa antes de
    # falar. O que precisa de teto aqui é o **estabelecimento** da conexão; o
    # prazo do stream inteiro já existe e é o `sse_timeout` (ADR-0026, item 5).
    app.state.redis = redis.from_url(  # type: ignore[no-untyped-call]  # `from_url` perdeu a anotação no redis 5.3.1, que o arq fixa (ver adapters/health.py); gatilho: o arq aceitar redis>=6
        settings.redis_url,
        socket_connect_timeout=settings.redis_connect_timeout,
    )

    app.state.storage = create_media_storage(settings)

    try:
        yield
    finally:
        await app.state.arq.aclose()
        await app.state.redis.aclose()
        # O pool de threads só do storage (CARD-026, ADR-0053). Sem este
        # `close()` as threads ficam vivas e o processo não termina — e o
        # sintoma não é erro, é a suíte demorando para encerrar.
        app.state.storage.close()
        # `dispose()` devolve as conexões do pool. Sem ele, subir e derrubar a
        # API num teste de integração vaza conexões entre casos.
        await engine.dispose()
