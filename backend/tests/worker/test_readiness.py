"""A chave de prontidão do worker (ADR-0025, item 3).

Fake de Redis: o que se verifica é o **desenho** — a chave só existe depois da
carga, tem TTL, é renovada, e some no desligamento limpo. O comportamento do
Redis em si é da biblioteca.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from voicecoach.worker.readiness import (
    HEARTBEAT_INTERVAL,
    READY_KEY,
    READY_TTL,
    WorkerReadiness,
)


class FakeRedis:
    def __init__(self, *, erro_apos: int | None = None) -> None:
        self.chaves: dict[str, timedelta] = {}
        self.escritas = 0
        self._erro_apos = erro_apos

    async def set(self, name: str, value: str, *, ex: timedelta, **_: Any) -> None:
        self.escritas += 1
        if self._erro_apos is not None and self.escritas > self._erro_apos:
            message = "redis caiu"
            raise ConnectionError(message)
        self.chaves[name] = ex

    async def delete(self, *names: str) -> int:
        removidas = [n for n in names if n in self.chaves]
        for n in removidas:
            del self.chaves[n]
        return len(removidas)


def readiness(redis: FakeRedis, **kwargs: Any) -> WorkerReadiness:
    return WorkerReadiness(redis, **kwargs)  # type: ignore[arg-type]


async def test_a_chave_nasce_com_ttl_e_morre_no_desligamento() -> None:
    redis = FakeRedis()
    r = readiness(redis)

    await r.start()
    assert redis.chaves == {READY_KEY: READY_TTL}

    await r.stop()
    assert redis.chaves == {}


async def test_o_heartbeat_renova_a_chave() -> None:
    """Renovação com intervalo minúsculo para o teste não esperar 10 s."""
    redis = FakeRedis()
    r = readiness(redis, ttl=timedelta(seconds=1), interval=timedelta(milliseconds=5))

    await r.start()
    await asyncio.sleep(0.03)
    await r.stop()

    assert redis.escritas > 1


async def test_o_intervalo_e_um_terco_do_ttl() -> None:
    """Duas renovações podem falhar sem derrubar a chave.

    Com intervalo = metade do TTL, uma única renovação perdida já apagaria o
    worker do readiness da API — e ele continuaria processando turns.
    """
    assert HEARTBEAT_INTERVAL * 3 == READY_TTL


async def test_falha_de_renovacao_nao_mata_o_heartbeat() -> None:
    """O worker segue capaz de trabalhar; a chave expira sozinha se for o caso.

    Deixar a exceção subir mataria a task de renovação de vez — e aí o worker
    trabalharia para sempre sem nunca mais se anunciar, que é pior do que o
    Redis piscar.
    """
    redis = FakeRedis(erro_apos=1)
    r = readiness(redis, ttl=timedelta(seconds=1), interval=timedelta(milliseconds=5))

    await r.start()
    await asyncio.sleep(0.03)
    escritas = redis.escritas
    await r.stop()

    assert escritas > 2  # continuou tentando depois de falhar
