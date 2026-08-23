"""O canal worker → API: nomes do fio, canal e tradução de erro.

Nenhum Redis de verdade: o que se verifica aqui é o **contrato** (o nome do
evento no fio, o canal e o payload), não o pub/sub, que é código da biblioteca.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from voicecoach.adapters.events.redis_turn_events import (
    RedisTurnEvents,
    channel_for,
    wire_name,
)
from voicecoach.application.ports.turn_events import (
    ChunkReady,
    Completed,
    Failed,
    FeedbackAvailable,
    Transcribed,
    TurnEvent,
    TurnEvents,
    TurnEventsError,
)


class FakeRedis:
    def __init__(self, *, erro: Exception | None = None) -> None:
        self.publicados: list[tuple[str, str]] = []
        self._erro = erro

    async def publish(self, channel: str, message: str) -> int:
        if self._erro is not None:
            raise self._erro
        self.publicados.append((channel, message))
        return 1


def adapter(**kwargs: Any) -> RedisTurnEvents:
    return RedisTurnEvents(FakeRedis(**kwargs))  # type: ignore[arg-type]


def test_o_adapter_satisfaz_a_porta() -> None:
    porta: TurnEvents = adapter()

    assert porta is not None


@pytest.mark.parametrize(
    ("evento", "esperado"),
    [
        (Transcribed(transcript="hi"), "transcribed"),
        (
            ChunkReady(index=0, storage_key="k", duration_seconds=1.0, text="hi"),
            "chunk",
        ),
        (
            FeedbackAvailable(has_mistakes=False, original="", corrected="", tip=""),
            "feedback",
        ),
        (Completed(reply_audio_key="k"), "completed"),
        (Failed(reason="x", delivered_partially=True), "failed"),
    ],
)
def test_os_nomes_do_fio_sao_os_do_adr_0026(evento: TurnEvent, esperado: str) -> None:
    """Os cinco nomes são contrato de API, não nome de classe.

    Renomear a dataclass não pode mudar o que o cliente recebe — por isso a
    tradução é uma tabela explícita e não `type(evento).__name__.lower()`.
    """
    assert wire_name(evento) == esperado


async def test_publica_no_canal_do_turn_com_o_payload_completo() -> None:
    redis = FakeRedis()
    eventos = RedisTurnEvents(redis)  # type: ignore[arg-type]
    turn_id = uuid4()

    await eventos.publish(
        turn_id,
        ChunkReady(index=2, storage_key="a/b/002.aac", duration_seconds=1.5, text="hi"),
    )

    canal, payload = redis.publicados[0]
    assert canal == f"voicecoach:turn:{turn_id}"
    assert json.loads(payload) == {
        "event": "chunk",
        "data": {
            "index": 2,
            "storage_key": "a/b/002.aac",
            "duration_seconds": 1.5,
            "text": "hi",
        },
    }


def test_o_canal_e_derivado_do_turn() -> None:
    turn_id = uuid4()

    assert channel_for(turn_id) == f"voicecoach:turn:{turn_id}"


async def test_falha_do_redis_atravessa_como_erro_da_porta() -> None:
    """`RedisError` não pode vazar para `application` — quem captura está lá."""
    eventos = adapter(erro=RedisConnectionError("sem conexão"))

    with pytest.raises(TurnEventsError, match="publicação falhou"):
        await eventos.publish(uuid4(), Completed(reply_audio_key="k"))
