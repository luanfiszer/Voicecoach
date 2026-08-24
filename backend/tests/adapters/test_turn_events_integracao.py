"""O canal contra um Redis de verdade — e a medição que justifica o SSE existir.

**Por que este arquivo existe além do `test_turn_events.py`.** Lá o Redis é um
dublê e o que se verifica é o contrato (nome do fio, canal, payload). Aqui o que
se verifica é o que um dublê nunca poderia provar: que o `SUBSCRIBE` funciona,
que a assinatura é desfeita ao sair do `async with`, e **quanto tempo** um evento
leva entre ser publicado e chegar ao consumidor.

Esse número é o critério de aceite do CARD-010 — *"o tempo entre o worker gravar
o trecho e o evento chegar é < 100 ms"* — e é ele que paga o ADR-0026. Sem
medição, a decisão de trocar polling por SSE é uma opinião.

Container próprio (`DockerContainer` genérico), como o MinIO do CARD-008: o teste
não depende de o `docker compose` do desenvolvedor estar de pé.
"""

from __future__ import annotations

import asyncio
import statistics
import time
from collections.abc import AsyncIterator, Iterator
from uuid import uuid4

import pytest
import redis.asyncio as redis
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import LogMessageWaitStrategy

from voicecoach.adapters.events.redis_turn_events import RedisTurnEvents
from voicecoach.application.ports.turn_events import (
    ChunkReady,
    Completed,
    Transcribed,
)

# O critério de aceite do card. Não é um número redondo escolhido por gosto: com
# polling a 500 ms a latência MÉDIA de descoberta é 250 ms, e o SSE só se paga se
# ficar numa ordem de grandeza abaixo disso.
LIMITE_MS = 100.0

TRECHOS = 6  # o pior caso de uma resposta do professor (ADR-0023)


@pytest.fixture(scope="session")
def redis_url() -> Iterator[str]:
    container = (
        DockerContainer("redis:7-alpine")
        .with_exposed_ports(6379)
        .waiting_for(LogMessageWaitStrategy("Ready to accept connections"))
    )
    with container:
        host = container.get_container_host_ip()
        porta = container.get_exposed_port(6379)
        yield f"redis://{host}:{porta}/0"


@pytest.fixture
async def canal(redis_url: str) -> AsyncIterator[RedisTurnEvents]:
    cliente: redis.Redis = redis.from_url(redis_url)  # type: ignore[no-untyped-call]  # ver adapters/health.py
    try:
        yield RedisTurnEvents(cliente)
    finally:
        await cliente.aclose()


async def test_o_que_e_publicado_chega_a_quem_assinou(
    canal: RedisTurnEvents,
) -> None:
    turn_id = uuid4()
    recebidos = []

    async with canal.subscribe(turn_id) as fluxo:
        await canal.publish(turn_id, Transcribed(transcript="hi there"))
        await canal.publish(turn_id, Completed(reply_audio_key="reply/full.aac"))
        async for evento in fluxo:
            recebidos.append(evento)
            if len(recebidos) == 2:
                break

    assert recebidos == [
        Transcribed(transcript="hi there"),
        Completed(reply_audio_key="reply/full.aac"),
    ]


async def test_a_assinatura_ja_existe_quando_o_async_with_devolve(
    canal: RedisTurnEvents,
) -> None:
    """A garantia da porta, contra Redis real.

    Publicar **imediatamente** depois do `__aenter__`, sem nunca ter iterado o
    fluxo, e ainda assim receber: é isso que o context manager compra sobre um
    gerador puro, e é o que permite ao caso de uso ler o banco sem abrir janela.
    """
    turn_id = uuid4()

    async with canal.subscribe(turn_id) as fluxo:
        await canal.publish(turn_id, Transcribed(transcript="publicado antes de ler"))
        # Só AGORA começamos a iterar.
        recebido = await asyncio.wait_for(anext(fluxo), timeout=5)

    assert recebido == Transcribed(transcript="publicado antes de ler")


async def test_sair_do_async_with_desfaz_a_assinatura(
    canal: RedisTurnEvents, redis_url: str
) -> None:
    """Assinatura que não some é conexão vazando por aluno que foi embora."""
    turn_id = uuid4()
    inspetor: redis.Redis = redis.from_url(redis_url)  # type: ignore[no-untyped-call]
    try:
        async with canal.subscribe(turn_id) as fluxo:
            await canal.publish(turn_id, Transcribed(transcript="x"))
            await asyncio.wait_for(anext(fluxo), timeout=5)
            durante = await inspetor.pubsub_numsub(f"voicecoach:turn:{turn_id}")

        # O Redis leva um instante para contabilizar o UNSUBSCRIBE.
        for _ in range(50):
            depois = await inspetor.pubsub_numsub(f"voicecoach:turn:{turn_id}")
            if depois[0][1] == 0:
                break
            await asyncio.sleep(0.02)

        assert durante[0][1] == 1
        assert depois[0][1] == 0
    finally:
        await inspetor.aclose()


async def test_o_evento_chega_em_menos_de_100ms(canal: RedisTurnEvents) -> None:
    """**O critério que justifica o SSE existir** (CARD-010).

    Mede o caminho inteiro do canal: `publish` → rede → `SUBSCRIBE` → JSON →
    `parse_wire` → dataclass. Seis trechos, que é o pior caso de uma resposta
    (ADR-0023).

    O que este número NÃO inclui: a serialização do evento para
    `text/event-stream`, que são microssegundos de `json.dumps` sobre quatro
    campos e não depende de rede. O que ele inclui é tudo que pode dar errado.
    """
    turn_id = uuid4()
    latencias_ms: list[float] = []

    async with canal.subscribe(turn_id) as fluxo:
        for i in range(TRECHOS):
            publicado_em = time.perf_counter()
            await canal.publish(
                turn_id,
                ChunkReady(
                    index=i,
                    storage_key=f"a/b/c/reply/{i:03d}.aac",
                    duration_seconds=1.5,
                    text=f"frase {i}",
                ),
            )
            evento = await asyncio.wait_for(anext(fluxo), timeout=5)
            latencias_ms.append((time.perf_counter() - publicado_em) * 1000)
            assert isinstance(evento, ChunkReady)
            assert evento.index == i

    pior = max(latencias_ms)
    # O número É o resultado deste teste: ele vai para o card e para o ADR.
    print(
        f"\nlatência do canal (n={TRECHOS}): "
        f"mediana {statistics.median(latencias_ms):.2f} ms | "
        f"pior {pior:.2f} ms | limite {LIMITE_MS:.0f} ms"
    )

    assert pior < LIMITE_MS
