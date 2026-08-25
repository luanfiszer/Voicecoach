"""Os três endpoints de Turn: aceitar, consultar e acompanhar (ADR-0026).

**As três rotas não são alternativas — são um contrato e a sua otimização.**

===============================  ==========================================
``POST /sessions/{id}/turns``    aceita a fala e devolve em milissegundos
``GET /turns/{id}``              a verdade completa. **É o contrato de recuo**
``GET /turns/{id}/events``       a mesma verdade, no instante em que acontece
===============================  ==========================================

O ADR-0026 item 4 é explícito: *"o SSE é uma otimização de latência sobre um
contrato que se sustenta sem ele"*. Um cliente que só use o ``GET`` leva um turn
até o fim. É por isso que o teste do recuo existe e não é opcional — o próprio
ADR registrou que dois caminhos de entrega precisam **ambos** ser testados, ou o
recuo apodrece.

**A URL assinada é montada aqui**, e só aqui (ADR-0035, item 4). O que trafega no
canal e o que está no banco é a ``storage_key``; assinar no worker produziria
URLs cujo TTL começou a contar na publicação — já envelhecidas quando alguém
reconectasse. Uma origem, um caminho de assinatura.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, assert_never
from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, Request, UploadFile, status
from sse_starlette.sse import EventSourceResponse

from voicecoach.adapters.events.redis_turn_events import wire_name
from voicecoach.api.audio_intake import extensao_para, medir
from voicecoach.api.dependencies import (
    get_settings_from_app,
    media_storage,
    start_turn_handler,
    stream_handler,
    turn_repository,
)
from voicecoach.api.errors import ProblemError
from voicecoach.api.schemas.problem import TYPE_SESSION_NOT_FOUND
from voicecoach.api.schemas.turns import (
    ChunkPayload,
    CompletedPayload,
    FailedPayload,
    FeedbackPayload,
    TranscribedPayload,
    TurnAcceptedResponse,
    TurnEventPayloads,
    TurnResponse,
)
from voicecoach.application.ports.media_storage import MediaStorage
from voicecoach.application.ports.repositories import TurnRepository
from voicecoach.application.ports.turn_events import (
    ChunkReady,
    Completed,
    Failed,
    FeedbackAvailable,
    Transcribed,
)
from voicecoach.application.result import Err, Ok
from voicecoach.application.use_cases.process_turn import TurnNotFoundError
from voicecoach.application.use_cases.start_turn import StartTurn, StartTurnHandler
from voicecoach.application.use_cases.stream_turn_events import (
    Delivery,
    StreamTurnEventsHandler,
    posicao,
)

# Ver a nota em `api/dependencies.py`: o FastAPI resolve as anotações em runtime,
# então o que aparece numa assinatura de rota não pode viver só sob TYPE_CHECKING.
from voicecoach.config import Settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from datetime import timedelta

router = APIRouter(tags=["turns"])

# Cabeçalhos que dizem a todo intermediário para não segurar a resposta.
#
# **Este é o risco silencioso do card**: um proxy que bufferize
# `text/event-stream` entrega todos os eventos juntos, no fim — e o produto fica
# exatamente tão lento quanto o polling que o SSE veio substituir, sem erro
# nenhum, sem log, sem nada quebrado. `X-Accel-Buffering: no` é a instrução que
# o nginx entende; `Cache-Control: no-cache` cobre caches intermediários.
#
# Hoje o `docker-compose.yml` deste repositório **não tem proxy** (verificado): o
# uvicorn é falado direto, e nada bufferiza. Os cabeçalhos vão mesmo assim,
# porque o dia em que um proxy entrar ninguém vai lembrar disto.
CABECALHOS_DE_STREAM = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}


@router.post(
    "/sessions/{session_id}/turns",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Envia a fala do aluno e enfileira o turno",
)
async def criar_turn(
    session_id: UUID,
    handler: Annotated[StartTurnHandler, Depends(start_turn_handler)],
    settings: Annotated[Settings, Depends(get_settings_from_app)],
    audio: Annotated[UploadFile, File(description="A fala do aluno.")],
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=8,
            max_length=255,
            description="Chave gerada pelo cliente. Reenviar a mesma devolve o "
            "mesmo turn_id, sem criar nem reprocessar nada.",
        ),
    ],
) -> TurnAcceptedResponse:
    """``202`` com o ``turn_id``. O trabalho começa depois da resposta.

    O cabeçalho é **obrigatório** de propósito. Torná-lo opcional ("se faltar, eu
    gero uma") faria o esquecimento do cliente virar um turno extra processado e
    pago, em silêncio — e a rede móvel, que é o caso de uso inteiro da
    idempotência, é justamente onde o reenvio acontece.
    """
    extensao = extensao_para(audio.content_type)
    bytes_do_aluno = await audio.read()
    duracao = await medir(bytes_do_aluno, maximo=settings.max_turn_audio_duration)

    resultado = await handler.handle(
        StartTurn(
            session_id=session_id,
            idempotency_key=idempotency_key,
            audio=bytes_do_aluno,
            content_type=audio.content_type or "application/octet-stream",
            extension=extensao,
            audio_duration=duracao,
        )
    )

    # `match` sobre o `Result`, terminando em `assert_never`: acrescentar um
    # desfecho ao caso de uso sem tratá-lo aqui quebra no mypy (ADR do Result).
    match resultado:
        case Ok(value=aceito):
            return TurnAcceptedResponse(
                turn_id=aceito.turn_id, replayed=aceito.replayed
            )
        case Err(error=ausente):
            raise ProblemError(
                type_=TYPE_SESSION_NOT_FOUND,
                title="Sessão não encontrada",
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"A sessão {ausente.session_id} não existe.",
                session_id=str(ausente.session_id),
            )
        case _:  # pragma: no cover - inalcançável enquanto o mypy passar
            assert_never(resultado)


@router.get(
    "/turns/{turn_id}",
    summary="O turno completo — o contrato de recuo (ADR-0026, item 4)",
)
async def obter_turn(
    turn_id: UUID,
    turns: Annotated[TurnRepository, Depends(turn_repository)],
    storage: Annotated[MediaStorage, Depends(media_storage)],
    settings: Annotated[Settings, Depends(get_settings_from_app)],
) -> TurnResponse:
    """Tudo que o app precisa mostrar, com as URLs já assinadas.

    Assinar N trechos são N HMACs locais (microssegundos cada, ADR-0024) — é o
    que torna aceitável entregar as URLs prontas em vez de o cliente pedir uma
    por trecho, que era o roundtrip por frase que o ADR-0024 recusou.
    """
    turn = await turns.get(turn_id)
    if turn is None:
        message = f"Turn {turn_id} não existe."
        raise TurnNotFoundError(message)

    ttl = settings.media_url_ttl
    urls = [
        await storage.presigned_get_url(chunk.storage_key, ttl)
        for chunk in turn.audio_chunks
    ]
    reply_url = (
        await storage.presigned_get_url(turn.reply_audio_ref, ttl)
        if turn.reply_audio_ref is not None
        else None
    )
    return TurnResponse.de_turn(turn, chunk_urls=urls, reply_audio_url=reply_url)


@router.get(
    "/turns/{turn_id}/events",
    summary="Entrega progressiva por SSE (ADR-0026)",
    response_class=EventSourceResponse,
    # **O `responses` aqui não é documentação decorativa** — é o que faz os cinco
    # payloads do SSE existirem no OpenAPI e, por consequência, nos tipos
    # gerados. Sem ele, quatro dos cinco eventos ficavam fora do contrato e o
    # cliente teria de escrevê-los à mão, que é o drift que o ADR-0008 proíbe.
    # Ver o docstring de `TurnEventPayloads`.
    # `response_model` e não `responses`: assim o media type sai do
    # `response_class` (`text/event-stream`) em vez de um `application/json`
    # que mentiria sobre o corpo. O FastAPI **não valida** o retorno quando o
    # endpoint devolve um `Response` — aqui ele é documentação e nada mais.
    response_model=TurnEventPayloads,
    # O `response_model` acima registra os cinco payloads em
    # `components.schemas`; este `responses` diz o media type de verdade e
    # aponta para eles. Com `responses` sozinho o FastAPI acrescentaria um
    # `application/json` que mentiria sobre o corpo do stream.
    responses={
        200: {
            "description": "Fluxo `text/event-stream`. Cada evento carrega, em "
            "`data`, o payload do seu `event:` — o mapa é `TurnEventPayloads`.",
            "content": {
                "text/event-stream": {
                    "schema": {"$ref": "#/components/schemas/TurnEventPayloads"}
                }
            },
        }
    },
)
async def acompanhar_turn(
    request: Request,
    turn_id: UUID,
    handler: Annotated[StreamTurnEventsHandler, Depends(stream_handler)],
    storage: Annotated[MediaStorage, Depends(media_storage)],
    settings: Annotated[Settings, Depends(get_settings_from_app)],
    last_event_id: Annotated[
        str | None,
        Header(
            alias="Last-Event-ID",
            description="O `id:` do último evento recebido. O servidor reenvia "
            "só o que vem depois dele, lendo do banco (ADR-0026, item 3).",
        ),
    ] = None,
) -> EventSourceResponse:
    """O stream. Fecha em ``completed``/``failed``, no prazo, ou no disconnect.

    **Quem fecha no disconnect é o `sse-starlette`**, e é o principal motivo de a
    biblioteca existir aqui: ele observa a mensagem ASGI ``http.disconnect`` e
    **cancela a corrotina** deste gerador. O cancelamento propaga para o
    ``async with`` da assinatura dentro do caso de uso, que desfaz o
    ``SUBSCRIBE`` e devolve a conexão do Redis. Sem isso, um aluno que fecha o
    app deixaria uma conexão pendurada até o prazo de 60 s — multiplicado por
    todo mundo.

    O `Last-Event-ID` chega por cabeçalho porque é assim que o `EventSource`
    nativo reconecta: ele o manda sozinho, sem o cliente escrever uma linha.
    """
    # **A validação acontece AQUI e não dentro do gerador**, e a razão é uma
    # propriedade do streaming que só aparece na primeira vez que se erra: assim
    # que o primeiro byte sai, o código HTTP já foi enviado — e um
    # `exception_handler` que dispare depois disso não tem mais o que fazer. O
    # Starlette é explícito ao recusar: *"Caught handled exception, but response
    # already started"*. Logo, tudo que pode virar 4xx tem de ser decidido antes
    # de a resposta começar.
    if last_event_id:
        posicao(last_event_id)

    fluxo = handler.stream(turn_id, last_event_id=last_event_id)
    return EventSourceResponse(
        _no_fio(fluxo, storage=storage, ttl=settings.media_url_ttl),
        headers=CABECALHOS_DE_STREAM,
    )


async def _no_fio(
    entregas: AsyncIterator[Delivery],
    *,
    storage: MediaStorage,
    ttl: timedelta,
) -> AsyncIterator[dict[str, str]]:
    """Traduz cada ``Delivery`` no dicionário que o ``sse-starlette`` serializa.

    O ``event:`` sai de ``wire_name`` — a **mesma** função que o worker usa para
    publicar no canal (ADR-0035, item 6). Os cinco nomes são contrato de API
    (ADR-0026) e não podem ter duas fontes; reescrevê-los aqui deixaria o
    ``assert_never`` de lá guardando metade da fronteira.
    """
    async for entrega in entregas:
        yield {
            "id": entrega.event_id,
            "event": wire_name(entrega.event),
            "data": await _payload(entrega, storage=storage, ttl=ttl),
        }


async def _payload(entrega: Delivery, *, storage: MediaStorage, ttl: timedelta) -> str:
    """O corpo do evento, em JSON — assinando o que for chave de storage."""
    match entrega.event:
        case Transcribed(transcript=texto):
            return TranscribedPayload(transcript=texto).model_dump_json()
        case ChunkReady() as trecho:
            return ChunkPayload(
                index=trecho.index,
                url=await storage.presigned_get_url(trecho.storage_key, ttl),
                duration_seconds=trecho.duration_seconds,
                text=trecho.text,
            ).model_dump_json()
        case FeedbackAvailable() as feedback:
            return FeedbackPayload(
                has_mistakes=feedback.has_mistakes,
                original=feedback.original,
                corrected=feedback.corrected,
                tip=feedback.tip,
            ).model_dump_json()
        case Completed(reply_audio_key=chave):
            return CompletedPayload(
                reply_audio_url=await storage.presigned_get_url(chave, ttl)
            ).model_dump_json()
        case Failed() as falha:
            return FailedPayload(
                reason=falha.reason,
                delivered_partially=falha.delivered_partially,
            ).model_dump_json()
        case _:  # pragma: no cover - inalcançável enquanto o mypy passar
            assert_never(entrega.event)
