"""Providers de dependência do FastAPI — a composição da camada de API.

`Depends` é o container de injeção do FastAPI. O que faz dele diferente de um
`IServiceCollection` é que o "registro" é a própria função: o parâmetro declara
`Depends(check_dependencies)` e o FastAPI chama aquela função. A substituição em
teste é feita por `app.dependency_overrides[funcao] = fake`, que é o mais perto
que se chega de trocar o registro do container num teste de integração.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Annotated
from uuid import UUID, uuid4

from fastapi import Depends, Request, status

# **Estes imports NÃO podem ficar sob `TYPE_CHECKING`.** Com
# `from __future__ import annotations`, toda anotação vira string — e o FastAPI
# RESOLVE as anotações em runtime (é assim que ele descobre o que injetar e o que
# validar). Um nome que só existe para o type checker produz um erro obscuro na
# geração do OpenAPI, não na importação do módulo. É a armadilha exata que
# `if TYPE_CHECKING` cria numa camada que faz introspecção.
from sqlalchemy.ext.asyncio import AsyncSession

from voicecoach.adapters.events.redis_turn_events import RedisTurnEvents
from voicecoach.adapters.health import (
    DependencyStatus,
    check_minio,
    check_postgres,
    check_redis,
    check_worker,
)
from voicecoach.adapters.persistence.repositories import (
    SqlAlchemySessionRepository,
    SqlAlchemyTurnRepository,
    SqlAlchemyUsageEventRepository,
)
from voicecoach.adapters.persistence.seed import DEV_STUDENT_ID
from voicecoach.adapters.persistence.unit_of_work import SqlAlchemyUnitOfWork
from voicecoach.adapters.queue.arq_turn_queue import ArqTurnQueue
from voicecoach.adapters.quota.redis_rate_limiter import RedisRateLimiter
from voicecoach.adapters.quota.redis_service_budget import RedisServiceBudget
from voicecoach.api.errors import ProblemError
from voicecoach.api.schemas.problem import TYPE_RATE_LIMITED
from voicecoach.application.ports.media_storage import MediaStorage
from voicecoach.application.ports.rate_limiter import RateLimiter
from voicecoach.application.ports.repositories import (
    SessionRepository,
    TurnRepository,
    UnitOfWork,
    UsageEventRepository,
)
from voicecoach.application.ports.service_budget import ServiceBudget
from voicecoach.application.ports.turn_events import TurnEvents
from voicecoach.application.ports.turn_queue import TurnQueue
from voicecoach.application.use_cases.discard_turn import DiscardTurnHandler
from voicecoach.application.use_cases.end_session import EndSessionHandler
from voicecoach.application.use_cases.read_quota_status import (
    ReadQuotaStatusHandler,
)
from voicecoach.application.use_cases.start_turn import StartTurnHandler
from voicecoach.application.use_cases.stream_turn_events import (
    StreamTurnEventsHandler,
)
from voicecoach.config import Settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


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


# ---------------------------------------------------------------------------
# A composição por request (CARD-010)
#
# **A regra que organiza tudo abaixo:** cada PORTA tem um provider próprio, e os
# handlers se montam a partir deles. É o que faz um teste de rota substituir seis
# funções por fakes e nunca tocar em Postgres, Redis ou MinIO — enquanto o
# caminho real continua sendo exatamente o mesmo grafo.
#
# Os recursos de processo (engine, pool do arq, conexão de pub/sub, cliente S3)
# vêm de `app.state`, onde o `lifespan` os pôs. Nada aqui os cria.
# ---------------------------------------------------------------------------


async def db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """A unidade de trabalho de UMA requisição.

    **Na API o dono da transação é a borda, por request** — ao contrário do
    worker, onde é o caso de uso, comitando por marco (ADR-0036). A diferença não
    é estilística: um turn no worker leva ~1,6 s e precisa que cada trecho fique
    visível para a retomada; um POST aqui é uma escrita só, e segurar a transação
    além dela seria segurar uma conexão do pool.

    Uma dependência com `yield` é o escopo: o que vem antes roda na entrada, o
    que vem depois (aqui, o `__aexit__` do `async with`) roda na saída — mesmo se
    o endpoint levantar. É o `services.AddScoped` do C#, com o descarte escrito à
    vista em vez de implícito no container.
    """
    factory = request.app.state.session_factory
    async with factory() as session:
        yield session


Sessao = Annotated[AsyncSession, Depends(db_session)]


def turn_repository(session: Sessao) -> TurnRepository:
    return SqlAlchemyTurnRepository(session)


def session_repository(session: Sessao) -> SessionRepository:
    return SqlAlchemySessionRepository(session)


def usage_event_repository(session: Sessao) -> UsageEventRepository:
    return SqlAlchemyUsageEventRepository(session)


def unit_of_work(session: Sessao) -> UnitOfWork:
    return SqlAlchemyUnitOfWork(session)


def media_storage(request: Request) -> MediaStorage:
    storage: MediaStorage = request.app.state.storage
    return storage


def turn_queue(request: Request) -> TurnQueue:
    return ArqTurnQueue(request.app.state.arq)


def turn_events(request: Request) -> TurnEvents:
    return RedisTurnEvents(request.app.state.redis)


def rate_limiter(request: Request) -> RateLimiter:
    return RedisRateLimiter(request.app.state.redis)


def service_budget(request: Request) -> ServiceBudget:
    settings = get_settings_from_app(request)
    return RedisServiceBudget(
        request.app.state.redis,
        daily_cap_usd=settings.daily_budget_usd,
        monthly_cap_usd=settings.monthly_budget_usd,
    )


def agora() -> datetime:
    """O relógio, injetável.

    Uma dependência e não `datetime.now()` dentro do handler pela mesma razão do
    worker: é o que permite a um teste afirmar *quando* algo foi criado sem
    depender do relógio da máquina.
    """
    return datetime.now(UTC)


def novo_turn_id() -> UUID:
    """O gerador de id, injetável — o teste precisa saber qual id esperar."""
    return uuid4()


async def enforce_turn_rate_limit(
    session_id: UUID,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings_from_app)],
    limiter: Annotated[RateLimiter, Depends(rate_limiter)],
) -> None:
    """Nega cedo, antes de ler o corpo do upload (ADR-0063, item 3).

    **Por `session_id`, não por "conta".** Este backend ainda não tem
    autenticação (achado desta mesma sessão de loop, CARD-043/045) — não há
    `student_id` a obter sem uma consulta ao banco, e o objetivo aqui é negar
    ANTES de qualquer IO caro. `session_id` já vem no path, de graça, e
    protege exatamente o padrão de abuso que o card teme (um cliente em loop
    contra a MESMA sessão) — quando a autenticação (CARD-049) existir, trocar
    a chave por `student_id`/conta é a extensão natural, não uma reescrita.

    `session_id` como PRIMEIRO parâmetro, sem `Depends`: é assim que o FastAPI
    lê um path param dentro de uma dependência — resolvido do mesmo path da
    rota que a usa, não de uma sub-rota própria.
    """
    ip = request.client.host if request.client else "sem-ip"
    dentro_da_sessao = await limiter.hit(
        f"turn-create:session:{session_id}",
        window=settings.turn_rate_limit_window,
        limit=settings.turn_rate_limit_per_student,
    )
    dentro_do_ip = await limiter.hit(
        f"turn-create:ip:{ip}",
        window=settings.turn_rate_limit_window,
        limit=settings.turn_rate_limit_per_ip,
    )
    if not (dentro_da_sessao and dentro_do_ip):
        raise ProblemError(
            type_=TYPE_RATE_LIMITED,
            title="Muitas requisições",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Limite de turns por minuto excedido. Tente novamente em instantes.",
            retry_after_seconds=int(settings.turn_rate_limit_window.total_seconds()),
        )


def start_turn_handler(
    turns: Annotated[TurnRepository, Depends(turn_repository)],
    sessions: Annotated[SessionRepository, Depends(session_repository)],
    usage_events: Annotated[UsageEventRepository, Depends(usage_event_repository)],
    uow: Annotated[UnitOfWork, Depends(unit_of_work)],
    storage: Annotated[MediaStorage, Depends(media_storage)],
    queue: Annotated[TurnQueue, Depends(turn_queue)],
    budget: Annotated[ServiceBudget, Depends(service_budget)],
    settings: Annotated[Settings, Depends(get_settings_from_app)],
    clock: Annotated[datetime, Depends(agora)],
    turn_id: Annotated[UUID, Depends(novo_turn_id)],
) -> StartTurnHandler:
    """Monta o handler do POST.

    `clock` e `turn_id` chegam como VALORES já resolvidos pelo FastAPI, e o
    handler pede `Callable`. As lambdas abaixo fazem a ponte: o valor foi
    calculado uma vez, no início da requisição, e o handler o lê quantas vezes
    quiser — que é o comportamento certo para um caso de uso que grava um
    instante só e usa um id só.
    """
    return StartTurnHandler(
        turns=turns,
        sessions=sessions,
        usage_events=usage_events,
        unit_of_work=uow,
        storage=storage,
        queue=queue,
        service_budget=budget,
        clock=lambda: clock,
        new_turn_id=lambda: turn_id,
        daily_quota_spoken=timedelta(minutes=settings.daily_audio_minutes_per_student),
        daily_quota_turns=settings.daily_quota_turns_per_student,
    )


def end_session_handler(
    sessions: Annotated[SessionRepository, Depends(session_repository)],
    uow: Annotated[UnitOfWork, Depends(unit_of_work)],
    clock: Annotated[datetime, Depends(agora)],
) -> EndSessionHandler:
    return EndSessionHandler(
        sessions=sessions,
        unit_of_work=uow,
        clock=lambda: clock,
    )


def read_quota_status_handler(
    usage_events: Annotated[UsageEventRepository, Depends(usage_event_repository)],
    budget: Annotated[ServiceBudget, Depends(service_budget)],
    settings: Annotated[Settings, Depends(get_settings_from_app)],
    clock: Annotated[datetime, Depends(agora)],
) -> ReadQuotaStatusHandler:
    return ReadQuotaStatusHandler(
        usage_events=usage_events,
        service_budget=budget,
        clock=lambda: clock,
        daily_quota_spoken=timedelta(minutes=settings.daily_audio_minutes_per_student),
        daily_quota_turns=settings.daily_quota_turns_per_student,
    )


def discard_turn_handler(
    turns: Annotated[TurnRepository, Depends(turn_repository)],
    sessions: Annotated[SessionRepository, Depends(session_repository)],
    uow: Annotated[UnitOfWork, Depends(unit_of_work)],
    clock: Annotated[datetime, Depends(agora)],
) -> DiscardTurnHandler:
    return DiscardTurnHandler(
        turns=turns,
        sessions=sessions,
        unit_of_work=uow,
        clock=lambda: clock,
    )


def requesting_student_id() -> UUID:
    """O aluno da requisição, para checagens de posse como a do CARD-032.

    Hoje é sempre ``DEV_STUDENT_ID`` (não há autenticação, ADR-0007) — mas a
    checagem de posse já existe no caso de uso, então o dia em que a auth
    chegar, só esta função muda (o token substitui a constante), e nenhuma
    linha do handler ou da rota precisa mudar junto.
    """
    return DEV_STUDENT_ID


def stream_handler(
    request: Request,
    turns: Annotated[TurnRepository, Depends(turn_repository)],
    events: Annotated[TurnEvents, Depends(turn_events)],
) -> StreamTurnEventsHandler:
    return StreamTurnEventsHandler(
        turns=turns,
        events=events,
        timeout=get_settings_from_app(request).sse_timeout,
    )
