"""``PasswordHasher`` sobre ``argon2-cffi`` (ADR-0007).

**Parâmetros explícitos** (CLAUDE.md: "suprimir/herdar parâmetro de segurança
é decisão, não atalho"). Os quatro abaixo são os *defaults* do
``argon2.PasswordHasher`` desde a versão 21 — e são, eles próprios, a
recomendação do OWASP Password Storage Cheat Sheet para ``argon2id`` (2023):
``time_cost=3``, ``memory_cost=65536`` (64 MiB), ``parallelism=4``,
``hash_len=32``. Escrevê-los por nome em vez de aceitar o construtor vazio é
o que torna a escolha visível a quem ler o código, e o que dá um lugar único
para mudar se um dia a régua do OWASP mudar.

**Por que ``run_in_executor``.** Ver o docstring da porta: ``argon2id`` é
CPU-bound de propósito, e um cálculo de ~50-100ms direto na corrotina
bloquearia o event loop único da API — a mesma classe de problema que o
``put_object`` síncrono do S3 resolveu com executor (ADR-0034), mas aqui é
CPU e não IO. Sem pool próprio: ao contrário do storage (ADR-0053, bulkhead
dedicado porque um upload pendurado poderia segurar uma thread por segundos),
aqui o teto é baixo e conhecido (~100ms), e o pool default do processo
(``min(32, cpu+4)``) não corre risco de ficar todo ocupado por logins.
"""

from __future__ import annotations

import asyncio
from functools import partial

from argon2 import PasswordHasher as _Argon2PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError


class Argon2PasswordHasher:
    """Implementa ``application.ports.password_hasher.PasswordHasher``."""

    def __init__(self) -> None:
        self._impl = _Argon2PasswordHasher(
            time_cost=3,
            memory_cost=65536,
            parallelism=4,
            hash_len=32,
        )

    async def hash(self, password: str) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._impl.hash, password)

    async def verify(self, password: str, password_hash: str) -> bool:
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(
                None, partial(self._impl.verify, password_hash, password)
            )
        except (VerificationError, InvalidHashError):
            # Dois tipos, e a herança NÃO os une: `VerifyMismatchError`
            # (senha errada) desce de `VerificationError`/`Argon2Error`, mas
            # `InvalidHashError` (hash mal formado — nunca deveria chegar
            # aqui vindo do banco, mas chegaria se algum dia um hash de
            # outro algoritmo fosse gravado por engano) desce de
            # `ValueError`, uma família à parte — capturar só `Verification
            # Error` deixa `InvalidHashError` escapar como bug não tratado.
            # Descoberto por teste (`test_hash_malformado_...`), não por
            # leitura da doc.
            return False
        return True
