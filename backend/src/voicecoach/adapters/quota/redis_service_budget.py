"""``ServiceBudget`` sobre dois contadores Redis, em centavos (ADR-0063, item 2).

**Centavos inteiros, não dólares em ponto flutuante.** `INCRBY` do Redis só
opera sobre inteiros; guardar `Decimal` serializado como string exigiria ler,
somar e escrever de volta — de novo a corrida get-then-set que este card existe
para evitar. Centavos é a menor unidade que o preço por token já produz sem
perda (`estimated_cost_usd` vem com mais casas que isso, mas o kill switch é
teto grosso, não faturamento por token).

**A chave leva a data/mês, não um TTL calculado.** `voicecoach:budget:daily:
2026-09-13` e `...monthly:2026-09` são chaves NOVAS a cada dia/mês — o
contador "reseta" sozinho por nunca mais ser incrementado, não por expirar no
segundo exato da virada. O TTL que este adapter põe (`_TTL_DIARIO`/
`_TTL_MENSAL`) existe só para o Redis não acumular chaves de dias/meses
passados para sempre; ele é generoso de propósito porque não é ele quem define
a semântica do reset.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from datetime import datetime

    from redis.asyncio import Redis

# A mesma zona da cota por student (ADR-0063): "hoje" e "este mês" são o
# calendário de Brasília, não o UTC em que o banco grava `occurred_at`.
FUSO = ZoneInfo("America/Sao_Paulo")

PREFIXO_DIARIO = "voicecoach:budget:daily:"
PREFIXO_MENSAL = "voicecoach:budget:monthly:"

# Generoso e sem relação com a virada real: só evita que chaves de dias/meses
# antigos vivam para sempre no Redis.
_TTL_DIARIO_SEGUNDOS = 3 * 24 * 3600
_TTL_MENSAL_SEGUNDOS = 40 * 24 * 3600

_CENTAVOS_POR_DOLAR = Decimal(100)


def _centavos(usd: Decimal) -> int:
    """Arredonda para o centavo mais próximo — nunca trunca silenciosamente."""
    return int((usd * _CENTAVOS_POR_DOLAR).to_integral_value(rounding=ROUND_HALF_UP))


def _chave_diaria(when: datetime) -> str:
    return f"{PREFIXO_DIARIO}{when.astimezone(FUSO).date().isoformat()}"


def _chave_mensal(when: datetime) -> str:
    local = when.astimezone(FUSO)
    return f"{PREFIXO_MENSAL}{local.year:04d}-{local.month:02d}"


class RedisServiceBudget:
    """Implementa ``ServiceBudget``. Os tetos entram prontos, na construção.

    ``application`` não pode importar ``config`` (ADR-0013) — quem lê
    ``Settings.daily_budget_usd``/``monthly_budget_usd`` e os passa aqui é a
    composition root, o mesmo padrão de todo outro adapter deste projeto que
    precisa de um número configurável.
    """

    def __init__(
        self, redis: Redis, *, daily_cap_usd: Decimal, monthly_cap_usd: Decimal
    ) -> None:
        self._redis = redis
        self._teto_diario = _centavos(daily_cap_usd)
        self._teto_mensal = _centavos(monthly_cap_usd)

    async def add_cost(self, usd: Decimal, *, when: datetime) -> None:
        centavos = _centavos(usd)
        chave_dia = _chave_diaria(when)
        chave_mes = _chave_mensal(when)
        await self._redis.incrby(chave_dia, centavos)
        await self._redis.expire(chave_dia, _TTL_DIARIO_SEGUNDOS)
        await self._redis.incrby(chave_mes, centavos)
        await self._redis.expire(chave_mes, _TTL_MENSAL_SEGUNDOS)

    async def is_exceeded(self, *, when: datetime) -> bool:
        gasto_dia, gasto_mes = await self._redis.mget(
            _chave_diaria(when), _chave_mensal(when)
        )
        # Chave ausente (nada gasto ainda hoje/este mês) vem `None` do MGET —
        # `int(None)` levantaria, então o `or 0` é o "zero é o normal" de
        # sempre, não um valor inventado para esconder erro.
        return (
            int(gasto_dia or 0) > self._teto_diario
            or int(gasto_mes or 0) > self._teto_mensal
        )
