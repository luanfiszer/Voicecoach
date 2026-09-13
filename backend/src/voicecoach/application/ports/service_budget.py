"""Porta do kill switch global por custo (ADR-0063, item 2).

**Diferença para a cota do CARD-015/ADR-0063 item 1.** Aquela é por *student*,
em minutos e turns; esta é **do produto inteiro**, em dólares. Um aluno dentro
da própria cota ainda pode ser recusado se o produto inteiro já gastou o
orçamento do dia ou do mês — os dois mecanismos são independentes e um não
substitui o outro.

**Por que soma em vez de reler o banco a cada request.** `UsageEventRepository`
já teria os dados (uma soma sem filtro por aluno), mas isso tornaria toda
verificação de kill switch uma varredura da tabela inteira de `usage_events` —
o oposto do índice `(student_id, occurred_at)` que aquela porta foi desenhada
para aproveitar. Somar em Redis, incrementado no momento em que o custo é
conhecido, é O(1) tanto para escrever quanto para ler.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from datetime import datetime
    from decimal import Decimal


class ServiceBudget(Protocol):
    """Os dois contadores (diário e mensal) do orçamento do produto.

    ``when`` entra em todo método, e não é lido internamente, pela mesma razão
    do ``clock`` do resto do projeto: um relógio próprio tornaria o adapter
    impossível de testar contra um instante fixo, e a janela do dia/mês
    depende de fuso (ADR-0063 usa `America/Sao_Paulo`, a mesma da cota).
    """

    async def add_cost(self, usd: Decimal, *, when: datetime) -> None:
        """Soma ao contador diário E ao mensal do instante ``when``."""
        ...

    async def is_exceeded(self, *, when: datetime) -> bool:
        """``True`` se o teto diário OU o mensal já estourou em ``when``."""
        ...
