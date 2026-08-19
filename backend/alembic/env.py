"""Ambiente do Alembic (ADR-0004).

Duas adaptações sobre o template ``async`` gerado pelo `alembic init`:

1. ``target_metadata`` aponta para os modelos, que é o que dá autogenerate.
2. A URL do banco **não** vem do ``alembic.ini``. Ordem de precedência:
   a URL injetada programaticamente (é assim que o teste aponta para o
   container descartável — ADR-0018) e, na falta dela, a configuração tipada da
   aplicação (ADR-0013). Deixar uma URL fixa no ``.ini`` versionado seria um
   segundo lugar onde a verdade mora, e o mais fácil de esquecer desatualizado.

Este arquivo fica fora do alcance do `ruff`/`mypy` dos gates (que rodam sobre
`src` e `tests`) — dívida registrada no card.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from voicecoach.adapters.persistence.models import Base
from voicecoach.config import get_settings

config = context.config

if config.config_file_name is not None:
    # `disable_existing_loggers=False` NÃO é detalhe: o default do template do
    # Alembic é `True`, e ele DESATIVA todo logger já criado no processo. Rodar
    # migration em processo (é o que os testes de adapter fazem, ADR-0018)
    # silenciava, por exemplo, o log de escolha do adapter de STT — descoberto
    # no CARD-006 por um teste que passava sozinho e falhava na suíte.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> str:
    """URL injetada pelo chamador, ou a da configuração da aplicação."""
    injected = config.get_main_option("sqlalchemy.url", None)
    if injected:
        return injected
    return get_settings().database_url


def run_migrations_offline() -> None:
    """Gera o SQL sem conectar (``alembic upgrade head --sql``)."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()

    connectable = async_engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
