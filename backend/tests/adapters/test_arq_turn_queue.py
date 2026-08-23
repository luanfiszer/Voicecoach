"""O adapter de fila: o nome da task e a tradução de erro.

O `arq` de verdade não sobe aqui — o que este arquivo protege é o **contrato
entre dois processos que não se importam**: a borda enfileira pelo nome, o
worker registra o mesmo nome, e nenhum dos dois importa o outro (ADR-0012).
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from voicecoach.adapters.queue.arq_turn_queue import PROCESS_TURN_TASK, ArqTurnQueue
from voicecoach.application.ports.turn_queue import TurnQueue, TurnQueueError


class FakeArqRedis:
    def __init__(self, *, erro: Exception | None = None) -> None:
        self.chamadas: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self._erro = erro

    async def enqueue_job(self, function: str, *args: Any, **kwargs: Any) -> None:
        if self._erro is not None:
            raise self._erro
        self.chamadas.append((function, args, kwargs))


def test_o_adapter_satisfaz_a_porta() -> None:
    porta: TurnQueue = ArqTurnQueue(FakeArqRedis())  # type: ignore[arg-type]

    assert porta is not None


async def test_enfileira_pelo_nome_do_contrato_com_o_id_como_texto() -> None:
    """O `turn_id` vai como `str`, não `UUID`.

    O `arq` serializa com `pickle` por default e um `UUID` sobreviveria — mas
    isso amarraria o formato do payload ao binário de uma versão de Python.
    """
    redis = FakeArqRedis()
    fila = ArqTurnQueue(redis)  # type: ignore[arg-type]
    turn_id = uuid4()

    await fila.enqueue(turn_id)

    função, args, kwargs = redis.chamadas[0]
    assert função == PROCESS_TURN_TASK
    assert args == (str(turn_id),)
    assert kwargs == {"_job_id": f"turn:{turn_id}"}


async def test_o_worker_registra_o_mesmo_nome_que_a_borda_enfileira() -> None:
    """Se este teste quebrar, os dois processos deixaram de se falar.

    É a única coisa que a borda e o worker combinam entre si, e é o tipo de
    divergência que não dá erro: os jobs simplesmente ficam na fila para sempre.
    """
    from voicecoach.worker.main import WorkerSettings

    nomes = {f.name for f in WorkerSettings.functions}

    assert nomes == {PROCESS_TURN_TASK}


async def test_falha_de_conexao_atravessa_como_erro_da_porta() -> None:
    fila = ArqTurnQueue(FakeArqRedis(erro=OSError("connection refused")))  # type: ignore[arg-type]

    with pytest.raises(TurnQueueError, match="não foi possível enfileirar"):
        await fila.enqueue(uuid4())
