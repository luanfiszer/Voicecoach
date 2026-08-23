"""Checks de disponibilidade das dependências de infraestrutura.

Mora em `adapters` porque é IO puro: fala com Postgres, Redis e MinIO de
verdade. Não há porta (`Protocol`) nem caso de uso em `application` — nenhuma
regra de negócio consome readiness, e porta sem segundo implementador é o
overengineering que a visão §F manda cortar (ADR-0014).
"""

from __future__ import annotations

import asyncio
import functools
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import asyncpg
import boto3
import redis.asyncio as redis
from botocore.config import Config as BotoConfig

if TYPE_CHECKING:
    from voicecoach.config import Settings

# Um readiness lento é pior que um readiness errado: quem consome quer resposta
# rápida. Se a dependência não responde em 2s, para este fim ela está fora.
_TIMEOUT_SECONDS = 2.0


@dataclass(frozen=True, slots=True)
class DependencyStatus:
    """Resultado de um check. `dataclass` ≈ record posicional do C#.

    `slots=True` troca o `__dict__` por slots fixos (menos memória, atributo
    novo em runtime vira erro); `frozen=True` o torna imutável.
    """

    name: str
    up: bool
    latency_ms: int
    error: str | None = None


def _elapsed_ms(started: float) -> int:
    # perf_counter, não time.time: monotônico, imune a ajuste de relógio.
    return int((time.perf_counter() - started) * 1000)


def _asyncpg_dsn(database_url: str) -> str:
    """Converte a URL do SQLAlchemy para a que o driver puro entende.

    `DATABASE_URL` carrega o dialeto do SQLAlchemy (`postgresql+asyncpg://`),
    porque é o CARD-005 quem mais vai consumi-la. O asyncpg usado direto aqui
    não conhece esse sufixo — é uma convenção do SQLAlchemy, não do Postgres.
    """
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def check_postgres(database_url: str) -> DependencyStatus:
    """Conecta e roda `SELECT 1` — prova que o banco responde, não só a porta."""
    started = time.perf_counter()
    try:
        # O `finally` aninhado (em vez de uma variável `conn = None` declarada
        # antes do try) existe por causa do type checker: como asyncpg não
        # publica anotações, `connect()` devolve `Any`, e atribuir `Any` a uma
        # variável declarada `Connection | None` não estreita o tipo — o mypy
        # continuaria vendo `None` no `.execute()`. Aqui a conexão só existe
        # depois de aberta, então não há `None` a considerar.
        connection = await asyncio.wait_for(
            asyncpg.connect(_asyncpg_dsn(database_url)), timeout=_TIMEOUT_SECONDS
        )
        try:
            await asyncio.wait_for(
                connection.execute("SELECT 1"), timeout=_TIMEOUT_SECONDS
            )
        finally:
            await connection.close()
        return DependencyStatus("postgres", up=True, latency_ms=_elapsed_ms(started))
    except Exception as exc:  # noqa: BLE001 — readiness reporta a falha, nunca propaga
        return DependencyStatus(
            "postgres", up=False, latency_ms=_elapsed_ms(started), error=_describe(exc)
        )


async def check_redis(redis_url: str) -> DependencyStatus:
    """PING/PONG — o handshake mais barato que prova protocolo, não só socket."""
    started = time.perf_counter()
    client = redis.from_url(
        redis_url,
        socket_connect_timeout=_TIMEOUT_SECONDS,
        socket_timeout=_TIMEOUT_SECONDS,
    )
    try:
        await asyncio.wait_for(client.ping(), timeout=_TIMEOUT_SECONDS)
        return DependencyStatus("redis", up=True, latency_ms=_elapsed_ms(started))
    except Exception as exc:  # noqa: BLE001 — idem: a falha vira status, não exceção
        return DependencyStatus(
            "redis", up=False, latency_ms=_elapsed_ms(started), error=_describe(exc)
        )
    finally:
        # `aclose()` devolve as conexões do pool. Sem isso, cada readiness
        # vazaria um pool — em endpoint chamado por probe, isso derruba a API.
        await client.aclose()


async def check_minio(settings: Settings) -> DependencyStatus:
    """`HEAD` no bucket, com credencial real — a dívida do ADR-0014 fecha aqui.

    Até o CARD-008 este check era um `GET /minio/health/live` não autenticado, e
    o próprio ADR-0014 registrou por quê: validar credencial e bucket exigia um
    cliente S3, que só entraria com a porta `MediaStorage`. Ele entrou.

    A diferença é a pergunta que o readiness passa a responder. O probe antigo
    dizia "o processo do MinIO está de pé". Este diz **"eu consigo trabalhar"** —
    e as três formas de falhar que o antigo deixava passar são justamente as que
    derrubam o primeiro turn do dia: credencial errada, bucket inexistente e
    permissão insuficiente. Um readiness que responde 200 nessas condições é o
    tipo de mentira que o ADR-0014 existe para não contar.

    Roda em executor como todo o resto do boto3 (ver `s3_media_storage.py`): num
    endpoint que já usa `asyncio.gather`, bloquear o loop atrasaria os outros
    dois checks e a latência reportada seria a soma, não o pior caso.
    """
    started = time.perf_counter()
    try:
        client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            config=BotoConfig(
                signature_version="s3v4",
                connect_timeout=_TIMEOUT_SECONDS,
                read_timeout=_TIMEOUT_SECONDS,
                retries={"max_attempts": 1},
            ),
        )
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, functools.partial(client.head_bucket, Bucket=settings.s3_bucket)
        )
        return DependencyStatus("minio", up=True, latency_ms=_elapsed_ms(started))
    except Exception as exc:  # noqa: BLE001 — idem: a falha vira status, não exceção
        return DependencyStatus(
            "minio", up=False, latency_ms=_elapsed_ms(started), error=_describe(exc)
        )


def _describe(exc: BaseException) -> str:
    """Mensagem curta e sem segredo — a URL do erro pode carregar senha."""
    if isinstance(exc, TimeoutError):
        return f"timeout after {_TIMEOUT_SECONDS:.0f}s"
    message = str(exc).strip()
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__
