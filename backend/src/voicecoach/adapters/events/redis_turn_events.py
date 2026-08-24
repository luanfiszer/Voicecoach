"""Canal worker → API por pub/sub Redis (ADR-0026 + o ADR de canal do CARD-009).

**Um canal por turn**, `voicecoach:turn:{turn_id}`. A alternativa era um canal
único com o `turn_id` no payload, e ela é pior aqui: o SSE do CARD-010 atende um
turn específico, então um canal global obrigaria cada conexão aberta a receber e
descartar os eventos de todos os outros alunos. Canal por turn é um `SUBSCRIBE` e
nenhum filtro — e o canal deixa de existir sozinho quando o último assinante sai,
porque no pub/sub não há nada a limpar.

**O preço, escrito:** pub/sub é *fire-and-forget*. Quem não está conectado no
instante da publicação nunca recebe. É aceitável exatamente porque este canal não
é a fonte da verdade — o banco é (ADR-0023), e a retomada por `Last-Event-ID`
sai de lá. Perder uma publicação custa latência, não dado. A exceção conhecida é
o evento `feedback`, que ainda não é persistido: dívida do CARD-013.

**JSON e não pickle**, ao contrário do payload do job na fila. O consumidor deste
canal reencaminha o conteúdo para um `text/event-stream`, que é texto por
definição; e o formato do fio deixa de depender da versão de Python dos dois
lados.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import TYPE_CHECKING, Any, assert_never

from redis.exceptions import RedisError

from voicecoach.application.ports.turn_events import (
    ChunkReady,
    Completed,
    Failed,
    FeedbackAvailable,
    Transcribed,
    TurnEventsError,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from uuid import UUID

    from redis.asyncio import Redis

    from voicecoach.application.ports.turn_events import TurnEvent

CHANNEL_PREFIX = "voicecoach:turn:"


def channel_for(turn_id: UUID) -> str:
    """O canal de um turn. Exportado porque o CARD-010 assina o mesmo nome."""
    return f"{CHANNEL_PREFIX}{turn_id}"


def wire_name(event: TurnEvent) -> str:
    """Traduz o evento interno no nome fixado pelo ADR-0026, item 1.

    A tradução é explícita, e não `type(event).__name__.lower()`, porque os
    nomes do fio são **contrato de API**: renomear a dataclass não pode mudar o
    que o cliente recebe. O `match` com `assert_never` é o que garante que
    acrescentar um evento novo à união quebre no `mypy`, e não em produção.
    """
    match event:
        case Transcribed():
            return "transcribed"
        case ChunkReady():
            return "chunk"
        case FeedbackAvailable():
            return "feedback"
        case Completed():
            return "completed"
        case Failed():
            return "failed"
        case _:  # pragma: no cover - inalcançável enquanto o mypy passar
            assert_never(event)


class UnknownWireEventError(ValueError):
    """Chegou pelo canal um nome de evento que este processo não conhece.

    Acontece quando um worker mais novo publica um evento que esta API ainda
    não sabe traduzir — deploy em duas velocidades. Levanta em vez de ignorar
    em silêncio: um evento descartado sem ruído é uma tela que fica parada sem
    ninguém saber por quê.
    """


def parse_wire(payload: str | bytes) -> TurnEvent:
    """O caminho inverso do ``wire_name`` + ``asdict``: fio → evento interno.

    **Por que a tradução é escrita duas vezes, e não derivada de uma tabela
    única.** Uma tabela `{Transcribed: "transcribed", ...}` casaria os dois
    lados por construção — e perderia o que o ADR-0035 item 6 comprou: o
    ``match`` com ``assert_never`` do ``wire_name``, que faz acrescentar um
    evento à união quebrar no ``mypy``. O que impede as duas metades de
    divergirem é o teste de ida-e-volta sobre os cinco eventos, e ele é barato.

    ``**data`` desempacota o dicionário nos parâmetros nomeados da dataclass —
    o equivalente de um `new Transcribed(transcript: ...)` montado a partir de
    um dicionário. Campo a mais ou a menos levanta ``TypeError`` na hora, que é
    o comportamento que se quer: o payload é contrato.
    """
    envelope: dict[str, Any] = json.loads(payload)
    nome: str = envelope["event"]
    data: dict[str, Any] = envelope["data"]
    match nome:
        case "transcribed":
            return Transcribed(**data)
        case "chunk":
            return ChunkReady(**data)
        case "feedback":
            return FeedbackAvailable(**data)
        case "completed":
            return Completed(**data)
        case "failed":
            return Failed(**data)
        case _:
            message = f"evento desconhecido no canal do turn: {nome!r}"
            raise UnknownWireEventError(message)


class RedisTurnEvents:
    """Implementa ``TurnEvents`` sobre o pub/sub do redis-py.

    Recebe o cliente pronto, como os outros adapters. Diferente do `boto3`, o
    `redis.asyncio` **é assíncrono de verdade** — não há executor aqui, e não
    deve haver: enfiar IO já async numa thread só adiciona um salto.
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def publish(self, turn_id: UUID, event: TurnEvent) -> None:
        payload = json.dumps(
            {"event": wire_name(event), "data": asdict(event)},
            ensure_ascii=False,
        )
        try:
            await self._redis.publish(channel_for(turn_id), payload)
        except RedisError as exc:
            message = f"publicação falhou no canal do turn {turn_id}: {exc}"
            raise TurnEventsError(message) from exc

    @asynccontextmanager
    async def subscribe(self, turn_id: UUID) -> AsyncIterator[AsyncIterator[TurnEvent]]:
        """Assina o canal do turn e só então devolve o iterador dos eventos.

        **`@asynccontextmanager` é o idioma sem paralelo direto em C#.** Ele
        transforma um gerador assíncrono de **um único `yield`** num context
        manager: o que vem antes do `yield` é o `__aenter__`, o que vem depois
        (inclusive o `finally` implícito do `async with` interno) é o
        `__aexit__`. Escrever a classe com `__aenter__`/`__aexit__` à mão daria
        no mesmo — isto é açúcar, e o mais perto em .NET seria um
        `IAsyncDisposable` cuja construção já fez o trabalho.

        A ordem aqui **é** o contrato da porta: `await assinatura.subscribe(...)`
        acontece antes do `yield`, então quem entrar no `async with` tem a
        garantia de que o canal já está assinado — e pode ir ler o banco sem
        perder o que for publicado nesse meio-tempo.

        **Uma conexão por assinante, e é por isso que o timeout do stream
        existe.** Cada `pubsub()` toma uma conexão do pool enquanto viver; o
        prazo do ADR-0026 item 5 é o que impede um turn esquecido de segurar
        uma para sempre.

        `ignore_subscribe_messages=True` filtra as confirmações que o Redis
        manda ao entrar no canal — sem isso, a primeira coisa que o cliente
        receberia seria a notícia de que ele se inscreveu.
        """
        try:
            async with self._redis.pubsub(ignore_subscribe_messages=True) as assinatura:
                await assinatura.subscribe(channel_for(turn_id))
                yield _eventos_de(assinatura)
        except RedisError as exc:
            message = f"assinatura falhou no canal do turn {turn_id}: {exc}"
            raise TurnEventsError(message) from exc


async def _eventos_de(assinatura: Any) -> AsyncIterator[TurnEvent]:  # noqa: ANN401 — o `PubSub` do redis-py não é anotado na 5.3.1 (ver `adapters/health.py`); gatilho: o arq aceitar redis>=6
    """Traduz cada mensagem do canal no evento interno correspondente.

    `listen()` é infinito de propósito: ele não sabe quando o turn acaba. Quem
    para é o consumidor, ao ver `completed`/`failed` ou ao estourar o prazo — e
    o `async with` de quem abriu a assinatura é que a desfaz.
    """
    async for mensagem in assinatura.listen():
        if mensagem.get("type") != "message":
            continue
        yield parse_wire(mensagem["data"])
