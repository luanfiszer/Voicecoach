"""Checks de disponibilidade das dependências de infraestrutura.

Mora em `adapters` porque é IO puro: fala com Postgres, Redis e MinIO de
verdade. Não há porta (`Protocol`) nem caso de uso em `application` — nenhuma
regra de negócio consome readiness, e porta sem segundo implementador é o
overengineering que a visão §F manda cortar (ADR-0014).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import asyncpg
import httpx
import redis.asyncio as redis

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
    conn: asyncpg.Connection[asyncpg.Record] | None = None
    try:
        conn = await asyncio.wait_for(
            asyncpg.connect(_asyncpg_dsn(database_url)), timeout=_TIMEOUT_SECONDS
        )
        await asyncio.wait_for(conn.execute("SELECT 1"), timeout=_TIMEOUT_SECONDS)
        return DependencyStatus("postgres", up=True, latency_ms=_elapsed_ms(started))
    except Exception as exc:  # readiness reporta a falha, nunca propaga
        return DependencyStatus(
            "postgres", up=False, latency_ms=_elapsed_ms(started), error=_describe(exc)
        )
    finally:
        if conn is not None:
            await conn.close()


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
    except Exception as exc:
        return DependencyStatus(
            "redis", up=False, latency_ms=_elapsed_ms(started), error=_describe(exc)
        )
    finally:
        # `aclose()` devolve as conexões do pool. Sem isso, cada readiness
        # vazaria um pool — em endpoint chamado por probe, isso derruba a API.
        await client.aclose()


async def check_minio(s3_endpoint_url: str) -> DependencyStatus:
    """GET no probe de liveness do MinIO — não autenticado, de propósito.

    Deliberadamente NÃO valida credencial nem existência do bucket: isso exige
    um cliente S3 (boto3), que entra com a porta `MediaStorage` no CARD-008.
    Aqui a pergunta é "o serviço está de pé?", não "consigo assinar URL?".
    """
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.get(f"{s3_endpoint_url.rstrip('/')}/minio/health/live")
            response.raise_for_status()
        return DependencyStatus("minio", up=True, latency_ms=_elapsed_ms(started))
    except Exception as exc:
        return DependencyStatus(
            "minio", up=False, latency_ms=_elapsed_ms(started), error=_describe(exc)
        )


def _describe(exc: BaseException) -> str:
    """Mensagem curta e sem segredo — a URL do erro pode carregar senha."""
    if isinstance(exc, TimeoutError):
        return f"timeout after {_TIMEOUT_SECONDS:.0f}s"
    message = str(exc).strip()
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__
