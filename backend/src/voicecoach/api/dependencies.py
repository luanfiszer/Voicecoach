"""Providers de dependência do FastAPI — a composição da camada de API.

`Depends` é o container de injeção do FastAPI. O que faz dele diferente de um
`IServiceCollection` é que o "registro" é a própria função: o parâmetro declara
`Depends(check_dependencies)` e o FastAPI chama aquela função. A substituição em
teste é feita por `app.dependency_overrides[funcao] = fake`, que é o mais perto
que se chega de trocar o registro do container num teste de integração.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Annotated
from uuid import UUID, uuid4

from fastapi import Depends, Header, Request, status

# **Estes imports NÃO podem ficar sob `TYPE_CHECKING`.** Com
# `from __future__ import annotations`, toda anotação vira string — e o FastAPI
# RESOLVE as anotações em runtime (é assim que ele descobre o que injetar e o que
# validar). Um nome que só existe para o type checker produz um erro obscuro na
# geração do OpenAPI, não na importação do módulo. É a armadilha exata que
# `if TYPE_CHECKING` cria numa camada que faz introspecção.
from sqlalchemy.ext.asyncio import AsyncSession

from voicecoach.adapters.auth.argon2_password_hasher import Argon2PasswordHasher
from voicecoach.adapters.auth.jwt_access_token_issuer import JwtAccessTokenIssuer
from voicecoach.adapters.events.redis_turn_events import RedisTurnEvents
from voicecoach.adapters.health import (
    DependencyStatus,
    check_minio,
    check_postgres,
    check_redis,
    check_worker,
)
from voicecoach.adapters.persistence.repositories import (
    SqlAlchemyCredentialRepository,
    SqlAlchemyEmailVerificationTokenRepository,
    SqlAlchemyPasswordResetTokenRepository,
    SqlAlchemyRefreshTokenRepository,
    SqlAlchemySessionRepository,
    SqlAlchemySocialIdentityRepository,
    SqlAlchemyStudentRepository,
    SqlAlchemyTranslationRepository,
    SqlAlchemyTurnRepository,
    SqlAlchemyUsageEventRepository,
)
from voicecoach.adapters.persistence.unit_of_work import SqlAlchemyUnitOfWork
from voicecoach.adapters.queue.arq_turn_queue import ArqTurnQueue
from voicecoach.adapters.quota.redis_rate_limiter import RedisRateLimiter
from voicecoach.adapters.quota.redis_service_budget import RedisServiceBudget
from voicecoach.api.errors import ProblemError
from voicecoach.api.schemas.auth import LoginRequest
from voicecoach.api.schemas.problem import (
    TYPE_DEPENDENCY_UNAVAILABLE,
    TYPE_EMAIL_NOT_VERIFIED,
    TYPE_RATE_LIMITED,
    TYPE_UNAUTHENTICATED,
)
from voicecoach.application.ports.access_tokens import (
    AccessTokenIssuer,
    InvalidAccessTokenError,
)
from voicecoach.application.ports.auth_repositories import (
    CredentialRepository,
    EmailVerificationTokenRepository,
    PasswordResetTokenRepository,
    RefreshTokenRepository,
    SocialIdentityRepository,
)
from voicecoach.application.ports.email_sender import EmailSender
from voicecoach.application.ports.media_storage import MediaStorage
from voicecoach.application.ports.password_hasher import PasswordHasher
from voicecoach.application.ports.rate_limiter import RateLimiter
from voicecoach.application.ports.repositories import (
    SessionRepository,
    StudentRepository,
    TranslationRepository,
    TurnRepository,
    UnitOfWork,
    UsageEventRepository,
)
from voicecoach.application.ports.service_budget import ServiceBudget
from voicecoach.application.ports.social_identity import SocialIdentityProvider
from voicecoach.application.ports.translator import Translator
from voicecoach.application.ports.turn_events import TurnEvents
from voicecoach.application.ports.turn_queue import TurnQueue
from voicecoach.application.use_cases.delete_account import (
    DeleteAccountHandler,
)
from voicecoach.application.use_cases.discard_turn import DiscardTurnHandler
from voicecoach.application.use_cases.email_verification import (
    ConfirmEmailHandler,
    ResendConfirmationHandler,
)
from voicecoach.application.use_cases.end_session import EndSessionHandler
from voicecoach.application.use_cases.list_sessions import ListSessionsHandler
from voicecoach.application.use_cases.login_student import LoginStudentHandler
from voicecoach.application.use_cases.login_with_social import LoginWithSocialHandler
from voicecoach.application.use_cases.logout_student import LogoutStudentHandler
from voicecoach.application.use_cases.password_reset import (
    RequestPasswordResetHandler,
    ResetPasswordHandler,
)
from voicecoach.application.use_cases.read_quota_status import (
    ReadQuotaStatusHandler,
)
from voicecoach.application.use_cases.refresh_tokens import RefreshTokensHandler
from voicecoach.application.use_cases.register_student import RegisterStudentHandler
from voicecoach.application.use_cases.start_turn import StartTurnHandler
from voicecoach.application.use_cases.stream_turn_events import (
    StreamTurnEventsHandler,
)
from voicecoach.application.use_cases.translate_text import TranslateTextHandler
from voicecoach.config import Settings, preco_do_modelo

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


def translation_repository(session: Sessao) -> TranslationRepository:
    return SqlAlchemyTranslationRepository(session)


def unit_of_work(session: Sessao) -> UnitOfWork:
    return SqlAlchemyUnitOfWork(session)


def media_storage(request: Request) -> MediaStorage:
    storage: MediaStorage = request.app.state.storage
    return storage


def turn_queue(request: Request) -> TurnQueue:
    return ArqTurnQueue(request.app.state.arq)


def turn_events(request: Request) -> TurnEvents:
    return RedisTurnEvents(request.app.state.redis)


def translator(request: Request) -> Translator:
    """O tradutor do processo, construído no `lifespan` (CARD-036)."""
    adapter: Translator = request.app.state.translator
    return adapter


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


def list_sessions_handler(
    sessions: Annotated[SessionRepository, Depends(session_repository)],
    settings: Annotated[Settings, Depends(get_settings_from_app)],
    clock: Annotated[datetime, Depends(agora)],
) -> ListSessionsHandler:
    """Monta o handler da listagem (CARD-030).

    A retenção entra como `timedelta` cru: é `retention_reply_chunk`, o prazo
    do TRECHO (o mais curto dos três, 1 dia) — e é ele que decide se a tela
    pode oferecer o play, porque é o trecho que a conversa reproduz.
    """
    return ListSessionsHandler(
        sessions=sessions,
        clock=lambda: clock,
        reply_media_retention=settings.retention_reply_chunk,
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


def password_hasher() -> PasswordHasher:
    return Argon2PasswordHasher()


def access_token_issuer(request: Request) -> AccessTokenIssuer:
    settings = get_settings_from_app(request)
    return JwtAccessTokenIssuer(
        secret=settings.jwt_secret, ttl=settings.access_token_ttl
    )


def credential_repository(session: Sessao) -> CredentialRepository:
    return SqlAlchemyCredentialRepository(session)


def refresh_token_repository(session: Sessao) -> RefreshTokenRepository:
    return SqlAlchemyRefreshTokenRepository(session)


def email_verification_token_repository(
    session: Sessao,
) -> EmailVerificationTokenRepository:
    return SqlAlchemyEmailVerificationTokenRepository(session)


def email_sender(request: Request) -> EmailSender:
    """O adapter escolhido no boot (ADR-0068) — do processo, como o `translator`."""
    sender: EmailSender = request.app.state.email_sender
    return sender


def verification_url(request: Request) -> Callable[[str], str]:
    """Monta o link de confirmação a partir do token em claro.

    ``public_api_base_url`` (não ``apiBaseUrl`` do cliente) porque quem clica
    o link é um cliente de e-mail, potencialmente fora da LAN — o mesmo
    raciocínio de `s3_public_endpoint_url` (ADR-0045), aplicado a auth.
    """
    settings = get_settings_from_app(request)
    base = settings.public_api_base_url.rstrip("/")
    return lambda token: f"{base}/v1/auth/confirm-email?token={token}"


def reset_password_url(request: Request) -> Callable[[str], str]:
    """O token de "esqueci minha senha", numa URL informativa.

    **Não é um link clicável de ação** — `POST /v1/auth/reset-password`
    precisa da senha nova no corpo, que nenhum e-mail pode coletar. Sem app
    web ainda (CARD-050/052), o e-mail existe para levar o token até o
    aluno; o formulário que o consome é trabalho de cliente, não deste card.
    """
    settings = get_settings_from_app(request)
    base = settings.public_api_base_url.rstrip("/")
    return lambda token: f"{base}/v1/auth/reset-password?token={token}"


def student_repository(session: Sessao) -> StudentRepository:
    return SqlAlchemyStudentRepository(session)


async def requesting_student_id(
    issuer: Annotated[AccessTokenIssuer, Depends(access_token_issuer)],
    students: Annotated[StudentRepository, Depends(student_repository)],
    authorization: Annotated[str | None, Header()] = None,
) -> UUID:
    """O aluno da requisição, do ``Bearer`` do ``Authorization`` (ADR-0007, CARD-049).

    **Antes desta função** o aluno era sempre ``DEV_STUDENT_ID`` — a troca é
    exatamente a linha única que o comentário antigo previa: o token
    substitui a constante, e nenhuma rota que já dependia desta função
    mudou uma linha (CARD-032, CARD-036, listagem de sessões, saldo de cota).

    **Desde o CARD-051/ADR-0069, esta função deixou de ser 100% stateless.**
    Além de decodificar o JWT, ela busca o `Student` e recusa (`401`) se a
    conta não existir ou tiver `deleted_at` preenchido. É o preço que o
    delete de conta exige pagar: o access token stateless de 15 min (ADR-0007)
    aceitava uma pequena janela pós-revogação como trade-off geral, mas o
    próprio ADR-0007 já registrava que ela **não** é tolerável no caso da
    exclusão — e este é o ponto único por onde toda rota autenticada passa,
    então é aqui que a checagem mora, uma vez, para nenhuma rota (presente ou
    futura) poder esquecê-la.
    """
    if authorization is None or not authorization.startswith("Bearer "):
        raise ProblemError(
            type_=TYPE_UNAUTHENTICATED,
            title="Não autenticado",
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Cabeçalho Authorization ausente ou fora do formato "
            "'Bearer <token>'.",
        )
    token = authorization.removeprefix("Bearer ").strip()
    try:
        student_id = issuer.decode(token)
    except InvalidAccessTokenError as exc:
        raise ProblemError(
            type_=TYPE_UNAUTHENTICATED,
            title="Não autenticado",
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    aluno = await students.get(student_id)
    if aluno is None or not aluno.is_active:
        raise ProblemError(
            type_=TYPE_UNAUTHENTICATED,
            title="Não autenticado",
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Esta conta não existe mais.",
        )
    return student_id


async def enforce_verified_email(
    student_id: Annotated[UUID, Depends(requesting_student_id)],
    credentials: Annotated[CredentialRepository, Depends(credential_repository)],
) -> None:
    """Barra o primeiro *turn* de quem não confirmou o e-mail (ADR-0007, item 4).

    **Login continua liberado** — só postar um turn é que exige e-mail
    verificado. A falta de credencial (aluno criado fora do fluxo de
    registro, ex.: seed de desenvolvimento) conta como não verificado —
    falha fechada, não aberta.
    """
    credential = await credentials.get_by_student_id(student_id)
    if credential is None or not credential.is_email_verified:
        raise ProblemError(
            type_=TYPE_EMAIL_NOT_VERIFIED,
            title="E-mail não confirmado",
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Confirme seu e-mail antes de gravar sua primeira fala. "
            "Reenviamos o link se você pedir (POST /v1/auth/resend-confirmation).",
        )


async def enforce_translation_rate_limit(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings_from_app)],
    limiter: Annotated[RateLimiter, Depends(rate_limiter)],
    student_id: Annotated[UUID, Depends(requesting_student_id)],
) -> None:
    """Limite próprio da tradução (CARD-036, RNF2).

    **Duas chaves, aluno e IP**, como no limite de turns e pela mesma razão:
    hoje o `student_id` é sempre `DEV_STUDENT_ID` (não há autenticação), então
    a chave por aluno é na prática um teto global — é a chave por IP que
    separa um cliente em loop dos demais. Quando a auth (CARD-049) chegar, a
    primeira passa a valer por conta sem que esta função mude.

    O teto por minuto é mais apertado que o de turns porque traduzir é um gesto
    de leitura: quem lê uma resposta pede uma tradução, não dez.
    """
    ip = request.client.host if request.client else "sem-ip"
    dentro_do_aluno = await limiter.hit(
        f"translate:student:{student_id}",
        window=settings.turn_rate_limit_window,
        limit=settings.translation_rate_limit_per_student,
    )
    dentro_do_ip = await limiter.hit(
        f"translate:ip:{ip}",
        window=settings.turn_rate_limit_window,
        limit=settings.turn_rate_limit_per_ip,
    )
    if not (dentro_do_aluno and dentro_do_ip):
        raise ProblemError(
            type_=TYPE_RATE_LIMITED,
            title="Muitas requisições",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Limite de traduções por minuto excedido. "
            "Tente novamente em instantes.",
            retry_after_seconds=int(settings.turn_rate_limit_window.total_seconds()),
        )


def translate_text_handler(
    turns: Annotated[TurnRepository, Depends(turn_repository)],
    sessions: Annotated[SessionRepository, Depends(session_repository)],
    translations: Annotated[TranslationRepository, Depends(translation_repository)],
    adapter: Annotated[Translator, Depends(translator)],
    budget: Annotated[ServiceBudget, Depends(service_budget)],
    uow: Annotated[UnitOfWork, Depends(unit_of_work)],
    clock: Annotated[datetime, Depends(agora)],
) -> TranslateTextHandler:
    """Monta o handler da tradução.

    `llm_price` entra como **função**, não como tabela: é a composition root
    quem conhece `config` (ADR-0013), e o caso de uso recebe a capacidade de
    perguntar o preço sem saber de onde ele vem — a mesma costura que o
    `ProcessTurnHandler` já usa.
    """
    return TranslateTextHandler(
        turns=turns,
        sessions=sessions,
        translations=translations,
        translator=adapter,
        service_budget=budget,
        unit_of_work=uow,
        clock=lambda: clock,
        llm_price=preco_do_modelo,
    )


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


# ---------------------------------------------------------------------------
# Auth (ADR-0007, CARD-049)
# ---------------------------------------------------------------------------


async def enforce_register_rate_limit(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings_from_app)],
    limiter: Annotated[RateLimiter, Depends(rate_limiter)],
) -> None:
    """Nega por IP antes do hash argon2id — cada tentativa custa CPU real."""
    ip = request.client.host if request.client else "sem-ip"
    dentro = await limiter.hit(
        f"auth-register:ip:{ip}",
        window=settings.register_rate_limit_window,
        limit=settings.register_rate_limit_per_ip,
    )
    if not dentro:
        raise ProblemError(
            type_=TYPE_RATE_LIMITED,
            title="Muitas requisições",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Limite de cadastros por IP excedido. Tente novamente mais tarde.",
            retry_after_seconds=int(
                settings.register_rate_limit_window.total_seconds()
            ),
        )


async def enforce_login_rate_limit(
    pedido: LoginRequest,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings_from_app)],
    limiter: Annotated[RateLimiter, Depends(rate_limiter)],
) -> None:
    """Por IP e por e-mail (CARD-049).

    ``pedido: LoginRequest`` como parâmetro de uma DEPENDÊNCIA, não só da
    rota: o FastAPI reconhece o mesmo modelo de corpo nos dois lugares e lê o
    JSON uma vez só — é o que permite negar por e-mail (o alvo real de uma
    varredura de senha) sem duplicar o parsing do corpo.
    """
    ip = request.client.host if request.client else "sem-ip"
    dentro_do_ip = await limiter.hit(
        f"auth-login:ip:{ip}",
        window=settings.auth_rate_limit_window,
        limit=settings.login_rate_limit_per_ip,
    )
    dentro_do_email = await limiter.hit(
        f"auth-login:email:{pedido.email}",
        window=settings.auth_rate_limit_window,
        limit=settings.login_rate_limit_per_email,
    )
    if not (dentro_do_ip and dentro_do_email):
        raise ProblemError(
            type_=TYPE_RATE_LIMITED,
            title="Muitas requisições",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Muitas tentativas de login. Tente novamente mais tarde.",
            retry_after_seconds=int(settings.auth_rate_limit_window.total_seconds()),
        )


def register_student_handler(
    students: Annotated[StudentRepository, Depends(student_repository)],
    credentials: Annotated[CredentialRepository, Depends(credential_repository)],
    verification_tokens: Annotated[
        EmailVerificationTokenRepository,
        Depends(email_verification_token_repository),
    ],
    hasher: Annotated[PasswordHasher, Depends(password_hasher)],
    sender: Annotated[EmailSender, Depends(email_sender)],
    uow: Annotated[UnitOfWork, Depends(unit_of_work)],
    clock: Annotated[datetime, Depends(agora)],
    settings: Annotated[Settings, Depends(get_settings_from_app)],
    url: Annotated[Callable[[str], str], Depends(verification_url)],
) -> RegisterStudentHandler:
    return RegisterStudentHandler(
        students=students,
        credentials=credentials,
        verification_tokens=verification_tokens,
        hasher=hasher,
        email_sender=sender,
        unit_of_work=uow,
        clock=lambda: clock,
        new_id=uuid4,
        verification_ttl=settings.email_verification_ttl,
        verification_url=url,
    )


def login_student_handler(
    credentials: Annotated[CredentialRepository, Depends(credential_repository)],
    students: Annotated[StudentRepository, Depends(student_repository)],
    refresh_tokens: Annotated[
        RefreshTokenRepository, Depends(refresh_token_repository)
    ],
    hasher: Annotated[PasswordHasher, Depends(password_hasher)],
    issuer: Annotated[AccessTokenIssuer, Depends(access_token_issuer)],
    uow: Annotated[UnitOfWork, Depends(unit_of_work)],
    clock: Annotated[datetime, Depends(agora)],
    settings: Annotated[Settings, Depends(get_settings_from_app)],
) -> LoginStudentHandler:
    return LoginStudentHandler(
        credentials=credentials,
        students=students,
        refresh_tokens=refresh_tokens,
        hasher=hasher,
        token_issuer=issuer,
        unit_of_work=uow,
        clock=lambda: clock,
        new_id=uuid4,
        access_token_ttl=settings.access_token_ttl,
        refresh_token_ttl=settings.refresh_token_ttl,
    )


def refresh_tokens_handler(
    refresh_tokens: Annotated[
        RefreshTokenRepository, Depends(refresh_token_repository)
    ],
    issuer: Annotated[AccessTokenIssuer, Depends(access_token_issuer)],
    uow: Annotated[UnitOfWork, Depends(unit_of_work)],
    clock: Annotated[datetime, Depends(agora)],
    settings: Annotated[Settings, Depends(get_settings_from_app)],
) -> RefreshTokensHandler:
    return RefreshTokensHandler(
        refresh_tokens=refresh_tokens,
        token_issuer=issuer,
        unit_of_work=uow,
        clock=lambda: clock,
        new_id=uuid4,
        access_token_ttl=settings.access_token_ttl,
        refresh_token_ttl=settings.refresh_token_ttl,
    )


def logout_student_handler(
    refresh_tokens: Annotated[
        RefreshTokenRepository, Depends(refresh_token_repository)
    ],
    uow: Annotated[UnitOfWork, Depends(unit_of_work)],
    clock: Annotated[datetime, Depends(agora)],
) -> LogoutStudentHandler:
    return LogoutStudentHandler(
        refresh_tokens=refresh_tokens,
        unit_of_work=uow,
        clock=lambda: clock,
    )


def confirm_email_handler(
    verification_tokens: Annotated[
        EmailVerificationTokenRepository,
        Depends(email_verification_token_repository),
    ],
    credentials: Annotated[CredentialRepository, Depends(credential_repository)],
    uow: Annotated[UnitOfWork, Depends(unit_of_work)],
    clock: Annotated[datetime, Depends(agora)],
) -> ConfirmEmailHandler:
    return ConfirmEmailHandler(
        verification_tokens=verification_tokens,
        credentials=credentials,
        unit_of_work=uow,
        clock=lambda: clock,
    )


def resend_confirmation_handler(
    credentials: Annotated[CredentialRepository, Depends(credential_repository)],
    verification_tokens: Annotated[
        EmailVerificationTokenRepository,
        Depends(email_verification_token_repository),
    ],
    sender: Annotated[EmailSender, Depends(email_sender)],
    uow: Annotated[UnitOfWork, Depends(unit_of_work)],
    clock: Annotated[datetime, Depends(agora)],
    settings: Annotated[Settings, Depends(get_settings_from_app)],
    url: Annotated[Callable[[str], str], Depends(verification_url)],
) -> ResendConfirmationHandler:
    return ResendConfirmationHandler(
        credentials=credentials,
        verification_tokens=verification_tokens,
        email_sender=sender,
        unit_of_work=uow,
        clock=lambda: clock,
        new_id=uuid4,
        verification_ttl=settings.email_verification_ttl,
        verification_url=url,
    )


def password_reset_token_repository(
    session: Sessao,
) -> PasswordResetTokenRepository:
    return SqlAlchemyPasswordResetTokenRepository(session)


async def enforce_password_reset_rate_limit(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings_from_app)],
    limiter: Annotated[RateLimiter, Depends(rate_limiter)],
) -> None:
    """Por IP (CARD-049) — mesma régua do registro: envia e-mail, custa dinheiro."""
    ip = request.client.host if request.client else "sem-ip"
    dentro = await limiter.hit(
        f"auth-password-reset:ip:{ip}",
        window=settings.register_rate_limit_window,
        limit=settings.register_rate_limit_per_ip,
    )
    if not dentro:
        raise ProblemError(
            type_=TYPE_RATE_LIMITED,
            title="Muitas requisições",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Limite de pedidos de redefinição de senha excedido.",
            retry_after_seconds=int(
                settings.register_rate_limit_window.total_seconds()
            ),
        )


def request_password_reset_handler(
    credentials: Annotated[CredentialRepository, Depends(credential_repository)],
    reset_tokens: Annotated[
        PasswordResetTokenRepository, Depends(password_reset_token_repository)
    ],
    sender: Annotated[EmailSender, Depends(email_sender)],
    uow: Annotated[UnitOfWork, Depends(unit_of_work)],
    clock: Annotated[datetime, Depends(agora)],
    settings: Annotated[Settings, Depends(get_settings_from_app)],
    url: Annotated[Callable[[str], str], Depends(reset_password_url)],
) -> RequestPasswordResetHandler:
    return RequestPasswordResetHandler(
        credentials=credentials,
        reset_tokens=reset_tokens,
        email_sender=sender,
        unit_of_work=uow,
        clock=lambda: clock,
        new_id=uuid4,
        reset_ttl=settings.password_reset_ttl,
        reset_url=url,
    )


def reset_password_handler(
    reset_tokens: Annotated[
        PasswordResetTokenRepository, Depends(password_reset_token_repository)
    ],
    credentials: Annotated[CredentialRepository, Depends(credential_repository)],
    refresh_tokens: Annotated[
        RefreshTokenRepository, Depends(refresh_token_repository)
    ],
    hasher: Annotated[PasswordHasher, Depends(password_hasher)],
    uow: Annotated[UnitOfWork, Depends(unit_of_work)],
    clock: Annotated[datetime, Depends(agora)],
) -> ResetPasswordHandler:
    return ResetPasswordHandler(
        reset_tokens=reset_tokens,
        credentials=credentials,
        refresh_tokens=refresh_tokens,
        hasher=hasher,
        unit_of_work=uow,
        clock=lambda: clock,
    )


# ---------------------------------------------------------------------------
# Delete de conta (CARD-051, ADR-0069)
# ---------------------------------------------------------------------------


async def enforce_delete_account_rate_limit(
    student_id: Annotated[UUID, Depends(requesting_student_id)],
    settings: Annotated[Settings, Depends(get_settings_from_app)],
    limiter: Annotated[RateLimiter, Depends(rate_limiter)],
) -> None:
    """Por conta, não por IP — é ação única e irreversível (CARD-051)."""
    dentro = await limiter.hit(
        f"delete-account:student:{student_id}",
        window=settings.delete_account_rate_limit_window,
        limit=settings.delete_account_rate_limit_per_student,
    )
    if not dentro:
        raise ProblemError(
            type_=TYPE_RATE_LIMITED,
            title="Muitas requisições",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Limite de pedidos de exclusão de conta excedido.",
            retry_after_seconds=int(
                settings.delete_account_rate_limit_window.total_seconds()
            ),
        )


def delete_account_handler(
    students: Annotated[StudentRepository, Depends(student_repository)],
    refresh_tokens: Annotated[
        RefreshTokenRepository, Depends(refresh_token_repository)
    ],
    uow: Annotated[UnitOfWork, Depends(unit_of_work)],
    clock: Annotated[datetime, Depends(agora)],
) -> DeleteAccountHandler:
    return DeleteAccountHandler(
        students=students,
        refresh_tokens=refresh_tokens,
        unit_of_work=uow,
        clock=lambda: clock,
    )


# ---------------------------------------------------------------------------
# Login social: Google e Apple (CARD-060, ADR-0070)
# ---------------------------------------------------------------------------


def google_identity_provider(request: Request) -> SocialIdentityProvider:
    """``None`` no `app.state` quando `GOOGLE_CLIENT_ID` não está configurado
    — CARD-060 não pôde ser fechado sem a credencial real (conta Google
    Cloud). ``503``, não ``500``: é a mesma disciplina do resto da API,
    "nunca um erro mudo" — aqui o motivo é "feature não configurada", não
    "dependência caiu", mas o desfecho para o cliente é o mesmo: tente
    outro caminho de login.
    """
    provider: SocialIdentityProvider | None = request.app.state.google_identity_provider
    if provider is None:
        raise ProblemError(
            type_=TYPE_DEPENDENCY_UNAVAILABLE,
            title="Provedor não configurado",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Login com Google não está disponível neste ambiente.",
        )
    return provider


def apple_identity_provider(request: Request) -> SocialIdentityProvider:
    """Mesma razão de ``google_identity_provider`` — sem `APPLE_CLIENT_ID`
    (o Services ID, não o bundle id) o app não pode verificar o
    `identityToken` contra a audiência certa.
    """
    provider: SocialIdentityProvider | None = request.app.state.apple_identity_provider
    if provider is None:
        raise ProblemError(
            type_=TYPE_DEPENDENCY_UNAVAILABLE,
            title="Provedor não configurado",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Login com Apple não está disponível neste ambiente.",
        )
    return provider


def social_identity_repository(session: Sessao) -> SocialIdentityRepository:
    return SqlAlchemySocialIdentityRepository(session)


async def enforce_social_login_rate_limit(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings_from_app)],
    limiter: Annotated[RateLimiter, Depends(rate_limiter)],
) -> None:
    """Por IP — mesmo teto de abuso do cadastro (CARD-049); a verificação
    criptográfica do token já limita o "confiar em qualquer coisa" que um
    endpoint de auth social convida (o card nomeia isto por escrito).
    """
    ip = request.client.host if request.client else "sem-ip"
    dentro = await limiter.hit(
        f"auth-social:ip:{ip}",
        window=settings.social_login_rate_limit_window,
        limit=settings.social_login_rate_limit_per_ip,
    )
    if not dentro:
        raise ProblemError(
            type_=TYPE_RATE_LIMITED,
            title="Muitas requisições",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Limite de tentativas de login social excedido.",
            retry_after_seconds=int(
                settings.social_login_rate_limit_window.total_seconds()
            ),
        )


def login_with_google_handler(
    identity_provider: Annotated[
        SocialIdentityProvider, Depends(google_identity_provider)
    ],
    social_identities: Annotated[
        SocialIdentityRepository, Depends(social_identity_repository)
    ],
    credentials: Annotated[CredentialRepository, Depends(credential_repository)],
    students: Annotated[StudentRepository, Depends(student_repository)],
    refresh_tokens: Annotated[
        RefreshTokenRepository, Depends(refresh_token_repository)
    ],
    issuer: Annotated[AccessTokenIssuer, Depends(access_token_issuer)],
    uow: Annotated[UnitOfWork, Depends(unit_of_work)],
    clock: Annotated[datetime, Depends(agora)],
    settings: Annotated[Settings, Depends(get_settings_from_app)],
) -> LoginWithSocialHandler:
    """Cada porta pelo seu provider overridável — nunca `SqlAlchemyXRepository(session)`
    direto, que contornaria `app.dependency_overrides` e quebraria todo
    teste de rota (a mesma composição por request do CARD-010).
    """
    return LoginWithSocialHandler(
        identity_provider=identity_provider,
        social_identities=social_identities,
        credentials=credentials,
        students=students,
        refresh_tokens=refresh_tokens,
        token_issuer=issuer,
        unit_of_work=uow,
        clock=lambda: clock,
        new_id=uuid4,
        access_token_ttl=settings.access_token_ttl,
        refresh_token_ttl=settings.refresh_token_ttl,
    )


def login_with_apple_handler(
    identity_provider: Annotated[
        SocialIdentityProvider, Depends(apple_identity_provider)
    ],
    social_identities: Annotated[
        SocialIdentityRepository, Depends(social_identity_repository)
    ],
    credentials: Annotated[CredentialRepository, Depends(credential_repository)],
    students: Annotated[StudentRepository, Depends(student_repository)],
    refresh_tokens: Annotated[
        RefreshTokenRepository, Depends(refresh_token_repository)
    ],
    issuer: Annotated[AccessTokenIssuer, Depends(access_token_issuer)],
    uow: Annotated[UnitOfWork, Depends(unit_of_work)],
    clock: Annotated[datetime, Depends(agora)],
    settings: Annotated[Settings, Depends(get_settings_from_app)],
) -> LoginWithSocialHandler:
    return LoginWithSocialHandler(
        identity_provider=identity_provider,
        social_identities=social_identities,
        credentials=credentials,
        students=students,
        refresh_tokens=refresh_tokens,
        token_issuer=issuer,
        unit_of_work=uow,
        clock=lambda: clock,
        new_id=uuid4,
        access_token_ttl=settings.access_token_ttl,
        refresh_token_ttl=settings.refresh_token_ttl,
    )
