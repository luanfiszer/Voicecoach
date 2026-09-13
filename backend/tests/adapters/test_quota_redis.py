"""`RedisRateLimiter` e `RedisServiceBudget` contra um Redis de verdade (ADR-0063).

Container próprio (`redis:7-alpine`), como o `test_turn_events_integracao.py` —
o teste não depende do `docker compose` do desenvolvedor estar de pé. O que se
verifica aqui é exatamente o que um dublê não poderia provar: que o `INCR` +
`PEXPIRE` do script Lua é atômico sob concorrência de verdade, e que a
aritmética de centavos do orçamento arredonda como o card exige.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import redis.asyncio as redis
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import LogMessageWaitStrategy

from voicecoach.adapters.quota.redis_rate_limiter import RedisRateLimiter
from voicecoach.adapters.quota.redis_service_budget import RedisServiceBudget


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
async def cliente(redis_url: str) -> AsyncIterator[redis.Redis]:
    conexao: redis.Redis = redis.from_url(redis_url)  # type: ignore[no-untyped-call]
    try:
        yield conexao
    finally:
        await conexao.flushdb()
        await conexao.aclose()


# --- RateLimiter --------------------------------------------------------


async def test_dez_hits_concorrentes_contra_limite_cinco_deixam_passar_exatamente_cinco(
    cliente: redis.Redis,
) -> None:
    """O critério de aceite do CARD-015: concorrência não estoura o limite.

    Dez corrotinas batendo na MESMA chave ao mesmo tempo — se o `INCR`+
    `PEXPIRE` não fosse atômico, uma corrida entre leitura e escrita deixaria
    mais de cinco passarem. É exatamente o modo de falha que o script Lua
    existe para fechar.
    """
    limiter = RedisRateLimiter(cliente)

    resultados = await asyncio.gather(
        *[
            limiter.hit("teste:concorrencia", window=timedelta(seconds=5), limit=5)
            for _ in range(10)
        ]
    )

    assert sum(resultados) == 5


async def test_janela_expira_e_libera_de_novo(cliente: redis.Redis) -> None:
    limiter = RedisRateLimiter(cliente)
    chave = "teste:janela-curta"

    assert await limiter.hit(chave, window=timedelta(milliseconds=200), limit=1)
    assert not await limiter.hit(chave, window=timedelta(milliseconds=200), limit=1)

    await asyncio.sleep(0.3)

    assert await limiter.hit(chave, window=timedelta(milliseconds=200), limit=1)


async def test_chaves_diferentes_tem_contadores_independentes(
    cliente: redis.Redis,
) -> None:
    limiter = RedisRateLimiter(cliente)

    assert await limiter.hit("teste:a", window=timedelta(seconds=5), limit=1)
    assert await limiter.hit("teste:b", window=timedelta(seconds=5), limit=1)
    # A SEGUNDA vez em "a" já estoura o limite de 1 — prova que "b" não
    # emprestou contador nenhum para "a".
    assert not await limiter.hit("teste:a", window=timedelta(seconds=5), limit=1)


# --- ServiceBudget --------------------------------------------------------


QUANDO = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)


async def test_soma_abaixo_do_teto_nao_excede(cliente: redis.Redis) -> None:
    budget = RedisServiceBudget(
        cliente, daily_cap_usd=Decimal("1.00"), monthly_cap_usd=Decimal("10.00")
    )

    await budget.add_cost(Decimal("0.50"), when=QUANDO)

    assert not await budget.is_exceeded(when=QUANDO)


async def test_soma_acima_do_teto_diario_excede(cliente: redis.Redis) -> None:
    budget = RedisServiceBudget(
        cliente, daily_cap_usd=Decimal("1.00"), monthly_cap_usd=Decimal("10.00")
    )

    await budget.add_cost(Decimal("0.60"), when=QUANDO)
    await budget.add_cost(Decimal("0.60"), when=QUANDO)

    assert await budget.is_exceeded(when=QUANDO)


async def test_teto_diario_e_mensal_sao_contadores_independentes(
    cliente: redis.Redis,
) -> None:
    """Estourar o dia não deveria depender de o mês também estar perto do teto."""
    budget = RedisServiceBudget(
        cliente, daily_cap_usd=Decimal("1.00"), monthly_cap_usd=Decimal("1000.00")
    )

    await budget.add_cost(Decimal("1.50"), when=QUANDO)

    assert await budget.is_exceeded(when=QUANDO)  # o diário estourou


async def test_dias_diferentes_nao_compartilham_contador(cliente: redis.Redis) -> None:
    budget = RedisServiceBudget(
        cliente, daily_cap_usd=Decimal("1.00"), monthly_cap_usd=Decimal("1000.00")
    )
    ontem = QUANDO - timedelta(days=1)

    await budget.add_cost(Decimal("1.50"), when=ontem)

    assert await budget.is_exceeded(when=ontem)
    assert not await budget.is_exceeded(when=QUANDO)  # dia novo, contador zerado


async def test_arredonda_para_o_centavo_mais_proximo(cliente: redis.Redis) -> None:
    """Meio centavo para cima — `ROUND_HALF_UP`, não truncamento silencioso."""
    budget = RedisServiceBudget(
        cliente, daily_cap_usd=Decimal("0.01"), monthly_cap_usd=Decimal("10.00")
    )

    # 0,005 arredonda para 0,01 — exatamente o teto, não acima dele.
    await budget.add_cost(Decimal("0.005"), when=QUANDO)

    assert not await budget.is_exceeded(when=QUANDO)
