"""Engine e fábrica de sessões (ADR-0004).

Recebe a URL por parâmetro em vez de ler ``voicecoach.config``: quem compõe é o
composition root (ADR-0013). Assim o teste aponta para o container descartável
sem mexer em variável de ambiente.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession as SqlAlchemyAsyncSession,
)


def create_engine(database_url: str, *, echo: bool = False) -> AsyncEngine:
    """Cria o engine — o pool de conexões do processo, criado uma vez só."""
    return create_async_engine(database_url, echo=echo)


def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[SqlAlchemyAsyncSession]:
    """Fábrica de unidades de trabalho.

    ``expire_on_commit=False`` é a diferença que mais surpreende quem vem do EF
    Core. O default do SQLAlchemy é **expirar** todos os objetos carregados no
    commit: o primeiro atributo lido depois disso dispara um SELECT novo para
    recarregá-los. Em código async isso é pior que lento — o recarregamento
    implícito acontece num acesso de atributo, que não é ``await``, e explode
    com ``MissingGreenlet`` em vez de esperar.

    Desligando, o objeto continua utilizável depois do commit, e qualquer
    recarga passa a ser decisão explícita. Pelo mesmo motivo não existe lazy
    loading de graça aqui: carregar relacionamento é escolha por caso de uso
    (``selectinload``), não efeito colateral de tocar num atributo — o contraste
    com o ``Include`` do EF Core aparece no CARD-013.
    """
    return async_sessionmaker(engine, expire_on_commit=False)
