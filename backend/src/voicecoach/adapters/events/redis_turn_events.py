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
from dataclasses import asdict
from typing import TYPE_CHECKING, assert_never

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
