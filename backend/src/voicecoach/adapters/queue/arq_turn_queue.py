"""Enfileiramento de turns com ``arq`` (ADR-0005).

**O nome da task mora aqui, não no worker**, e é a única coisa que os dois
processos precisam combinar. `api` e `worker` são camadas irmãs que não se
importam (ADR-0012); se a borda importasse a função da task para enfileirá-la
pelo objeto, essa seta existiria — e o `lint-imports` a reprovaria. Uma string
compartilhada num adapter que ambos podem importar é o acoplamento mínimo
possível entre um produtor e um consumidor que não se conhecem.

Equivalente mental .NET: o nome da fila/rota numa constante compartilhada, em
vez de o publisher referenciar o assembly do consumer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from arq.connections import ArqRedis

from voicecoach.application.ports.turn_queue import TurnQueueError

if TYPE_CHECKING:
    from uuid import UUID

# O contrato entre a borda e o worker. Mudar esta string com jobs em voo faz o
# worker novo ignorar o que o antigo enfileirou — deploy é que tem de coordenar,
# não o código.
PROCESS_TURN_TASK = "process_turn"


class ArqTurnQueue:
    """Implementa ``TurnQueue`` sobre uma conexão ``arq``.

    Recebe o ``ArqRedis`` pronto em vez de criá-lo: a conexão é do processo
    (pool), não da operação, e quem decide o momento de abri-la e fechá-la é a
    composition root — o mesmo desenho do `S3MediaStorage`, que recebe o cliente
    boto3 montado.
    """

    def __init__(self, redis: ArqRedis) -> None:
        self._redis = redis

    async def enqueue(self, turn_id: UUID) -> None:
        """Publica o job e descarta o ``Job`` que o arq devolve.

        O ``turn_id`` viaja como ``str``: o arq serializa os argumentos com
        ``pickle`` por default, e um ``UUID`` sobreviveria — mas fazer o payload
        depender do formato binário de uma versão de Python é o tipo de
        acoplamento que só aparece quando alguém troca o serializador.

        ``enqueue_job`` devolve ``None`` quando existe um job com o mesmo
        ``_job_id`` ainda pendente. Aqui isso **não** é erro: é a fila fazendo
        exatamente o que se pediu — um turn, um job. O `Idempotency-Key` da
        borda é outro problema, e é do CARD-010.
        """
        try:
            await self._redis.enqueue_job(
                PROCESS_TURN_TASK, str(turn_id), _job_id=f"turn:{turn_id}"
            )
        except (OSError, RuntimeError) as exc:
            message = f"não foi possível enfileirar o turn {turn_id}: {exc}"
            raise TurnQueueError(message) from exc
