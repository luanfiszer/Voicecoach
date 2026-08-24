"""A tradução de erro do núcleo para HTTP — o único lugar onde ela acontece.

O ADR-0017 prometeu esta borda (*"um exception handler único em ``api/`` converte
``DomainError`` em Problem Details"*) e ela nunca tinha sido escrita: até o
CARD-010 o app não tinha ``exception_handler`` nenhum.

**O princípio, e é o que faz a lista abaixo não ser arbitrária:** o código HTTP
responde à pergunta *"de quem é o problema?"*.

=================================  ======  ==========================================
Exceção                            HTTP    Por quê
=================================  ======  ==========================================
``RequestValidationError``         422     o cliente mandou algo que não é aceitável
``ProblemError``                   ela     validação de negócio da borda, com o
                                           código que o próprio problema declara
``TurnNotFoundError``              404     o recurso não existe
``MalformedEventIdError``          400     o ``Last-Event-ID`` não é deste esquema
``DomainError``                    409     invariante do agregado: o estado atual
                                           não permite o que se pediu
infraestrutura de porta            503     não é culpa do cliente e **pode passar**
=================================  ======  ==========================================

**Não há handler para ``Exception``**, e a omissão é decisão. Um handler
genérico transformaria todo bug num 500 bonitinho e — o que importa mais —
faria o ``httpx`` dos testes **parar de propagar** a exceção, escondendo em
verde exatamente o que deveria falhar em vermelho. 500 não é contrato; é bug, e
bug tem de doer.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from voicecoach.adapters.events.redis_turn_events import UnknownWireEventError
from voicecoach.api.schemas.problem import (
    CONTENT_TYPE,
    TYPE_DEPENDENCY_UNAVAILABLE,
    TYPE_INVALID_EVENT_ID,
    TYPE_INVALID_STATE,
    TYPE_TURN_NOT_FOUND,
    TYPE_VALIDATION,
    ProblemDetails,
)
from voicecoach.application.ports.media_storage import MediaStorageError
from voicecoach.application.ports.repositories import ConflictingWriteError
from voicecoach.application.ports.turn_events import TurnEventsError
from voicecoach.application.ports.turn_queue import TurnQueueError
from voicecoach.application.use_cases.process_turn import TurnNotFoundError
from voicecoach.application.use_cases.stream_turn_events import MalformedEventIdError
from voicecoach.domain.errors import DomainError

logger = logging.getLogger(__name__)

# As falhas de porta que significam "a infraestrutura não colaborou". Todas
# herdam de `RuntimeError` e nenhuma de `DomainError` — é a distinção do
# ADR-0017, e é por isso que esta tupla pode existir sem `isinstance` espalhado.
FALHAS_DE_INFRAESTRUTURA = (
    TurnQueueError,
    MediaStorageError,
    TurnEventsError,
    ConflictingWriteError,
    UnknownWireEventError,
)


class ProblemError(Exception):
    """Um desfecho que a borda já sabe descrever como Problem Details.

    Existe para que a validação de entrada da rota (content type recusado,
    áudio longo demais, cabeçalho ausente) produza **o mesmo formato** que os
    erros do núcleo, sem que a rota monte `JSONResponse` na mão. Levantar é o
    que permite validar no meio de uma função e sair — o `HTTPException` do
    FastAPI faria isso, mas com o corpo `{"detail": ...}` dele, que é outro
    contrato.
    """

    def __init__(
        self,
        *,
        type_: str,
        title: str,
        status_code: int,
        detail: str | None = None,
        **extensions: Any,  # noqa: ANN401 — são os *extension members* da RFC 9457: valores JSON arbitrários por tipo de problema
    ) -> None:
        super().__init__(detail or title)
        self.problem = details(
            type_=type_,
            title=title,
            status_code=status_code,
            detail=detail,
            **extensions,
        )


def details(
    *,
    type_: str,
    title: str,
    status_code: int,
    detail: str | None = None,
    **extensions: Any,  # noqa: ANN401 — *extension members* da RFC 9457
) -> ProblemDetails:
    """Monta o problema, extensões incluídas.

    **Por que ``model_validate`` sobre um dicionário e não o construtor.**
    ``extra="allow"`` é uma regra de *runtime* do pydantic; o ``mypy`` continua
    conhecendo só os quatro campos declarados e reprova
    ``ProblemDetails(errors=...)`` com ``unexpected keyword argument``. Validar
    um dicionário mantém as extensões possíveis **e** o tipo checado — em vez de
    a alternativa óbvia, que seria um ``# type: ignore`` por chamada.
    """
    return ProblemDetails.model_validate(
        {
            "type": type_,
            "title": title,
            "status": status_code,
            "detail": detail,
            **extensions,
        }
    )


def problem_response(problem: ProblemDetails) -> JSONResponse:
    """Serializa o problema com o content type que a RFC 9457 exige."""
    return JSONResponse(
        status_code=problem.status,
        content=problem.model_dump(mode="json", exclude_none=True),
        media_type=CONTENT_TYPE,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Liga os handlers ao app. Chamado uma vez, no ``create_app()``."""

    @app.exception_handler(ProblemError)
    async def _problema(_: Request, exc: ProblemError) -> JSONResponse:
        return problem_response(exc.problem)

    @app.exception_handler(RequestValidationError)
    async def _validacao(_: Request, exc: RequestValidationError) -> JSONResponse:
        # `exc.errors()` traz a lista do pydantic (campo, tipo do erro, valor).
        # Ela vai como *extension member* `errors`, e não achatada em `detail`:
        # o cliente que quiser marcar o campo errado na tela precisa da lista,
        # e quem só loga precisa da frase.
        return problem_response(
            details(
                type_=TYPE_VALIDATION,
                title="Requisição inválida",
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="O corpo ou os parâmetros da requisição não são válidos.",
                errors=exc.errors(),
            )
        )

    @app.exception_handler(TurnNotFoundError)
    async def _turn_ausente(_: Request, exc: TurnNotFoundError) -> JSONResponse:
        return problem_response(
            details(
                type_=TYPE_TURN_NOT_FOUND,
                title="Turno não encontrado",
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            )
        )

    @app.exception_handler(MalformedEventIdError)
    async def _id_invalido(_: Request, exc: MalformedEventIdError) -> JSONResponse:
        return problem_response(
            details(
                type_=TYPE_INVALID_EVENT_ID,
                title="Last-Event-ID inválido",
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            )
        )

    @app.exception_handler(DomainError)
    async def _dominio(_: Request, exc: DomainError) -> JSONResponse:
        # 409 e não 400: a requisição está bem formada — é o **estado** do
        # recurso que não permite a operação. É o caso da fala gravada offline
        # que chega depois de a sessão ter sido encerrada (ver `Session`).
        return problem_response(
            details(
                type_=TYPE_INVALID_STATE,
                title="Operação incompatível com o estado atual",
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            )
        )

    for falha in FALHAS_DE_INFRAESTRUTURA:
        app.add_exception_handler(falha, _infraestrutura)


async def _infraestrutura(_: Request, exc: Exception) -> JSONResponse:
    """503 e log com stack: o cliente pode tentar de novo, nós temos de olhar.

    Nunca repassa ``str(exc)`` ao cliente. A mensagem de uma falha de conexão
    costuma carregar host, porta e, no pior caso, credencial embutida na URL —
    é a mesma precaução do ``_describe`` do readiness.
    """
    logger.exception("falha de infraestrutura atendendo requisição", exc_info=exc)
    return problem_response(
        details(
            type_=TYPE_DEPENDENCY_UNAVAILABLE,
            title="Dependência indisponível",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Uma dependência do serviço não respondeu. Tente novamente.",
        )
    )
