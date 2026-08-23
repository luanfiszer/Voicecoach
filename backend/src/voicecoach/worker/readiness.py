"""A chave que diz "os modelos estão carregados" (ADR-0025, item 3).

**O problema que ela resolve.** O `arq` não consome job enquanto o `on_startup`
não retorna — essa parte é comportamento da biblioteca e não precisa de código
nosso. O que a biblioteca não faz é contar isso a **outro processo**: a API
precisa responder `GET /health/ready` sabendo se existe worker capaz de honrar a
fila, e "o container subiu" não é a mesma pergunta que "os modelos carregaram".

**Por que uma chave com TTL e não uma chave simples.** Worker que morre não
apaga nada — ele morre. Uma chave permanente sobreviveria ao processo e a API
passaria a afirmar "pronto" sobre um worker inexistente, que é precisamente a
mentira que o ADR-0025 existe para matar. Com TTL curto e renovação periódica, o
silêncio do worker apaga a chave sozinho: o estado "pronto" **expira** em vez de
ser desmentido por alguém.

Equivalente mental .NET: um heartbeat de health check registrado num store
externo, do tipo que um `IHostedService` renova em background — com a diferença
de que aqui a expiração é do Redis, não de um timer que também poderia morrer.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from voicecoach.adapters.readiness_keys import (
    WORKER_HEARTBEAT_INTERVAL,
    WORKER_READY_KEY,
    WORKER_READY_TTL,
)

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)

# Reexportados com o nome curto para quem lê este módulo. A definição mora em
# `adapters/readiness_keys.py` porque a API também precisa dela, e `adapters`
# não pode importar `worker` — o `lint-imports` reprovou o desenho inverso.
READY_KEY = WORKER_READY_KEY
READY_TTL = WORKER_READY_TTL
HEARTBEAT_INTERVAL = WORKER_HEARTBEAT_INTERVAL


class WorkerReadiness:
    """Publica e renova a prontidão do worker enquanto ele viver."""

    def __init__(
        self,
        redis: Redis,
        *,
        key: str = READY_KEY,
        ttl: timedelta = READY_TTL,
        interval: timedelta = HEARTBEAT_INTERVAL,
    ) -> None:
        self._redis = redis
        self._key = key
        self._ttl = ttl
        self._interval = interval
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Grava a chave e começa a renová-la. Chamado **depois** da carga."""
        await self._marcar()
        self._task = asyncio.create_task(self._heartbeat(), name="worker-readiness")

    async def stop(self) -> None:
        """Para de renovar e apaga a chave — desligamento limpo é imediato.

        Sem isto, um `docker compose down` deixaria a API afirmando "pronto" por
        até `READY_TTL` depois de o worker já ter ido embora. O TTL é a rede de
        segurança para a morte **súbita**; para a morte anunciada, apagar é mais
        honesto.
        """
        if self._task is not None:
            self._task.cancel()
            # `contextlib.suppress` é um context manager que engole a exceção
            # nomeada — o `try/except X: pass` em uma linha. Aqui ele existe
            # porque cancelar uma task SEMPRE levanta `CancelledError` em quem a
            # aguarda, e essa é a confirmação de que funcionou, não uma falha.
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await self._redis.delete(self._key)

    async def _marcar(self) -> None:
        await self._redis.set(self._key, "1", ex=self._ttl)

    async def _heartbeat(self) -> None:
        while True:
            await asyncio.sleep(self._interval.total_seconds())
            try:
                await self._marcar()
            except Exception:
                # A renovação falhar não pode derrubar o worker: ele continua
                # capaz de processar turns, e a consequência de não renovar já
                # está desenhada — a chave expira e a API para de dizer "pronto".
                # Deixar a exceção subir mataria a task de heartbeat de vez, o
                # que é pior: o worker seguiria trabalhando e nunca mais se
                # anunciaria.
                logger.exception("readiness: falha ao renovar %s", self._key)
