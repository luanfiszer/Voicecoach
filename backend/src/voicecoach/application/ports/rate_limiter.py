"""Porta de rate limit — proteção contra *loop* de cliente (ADR-0063, item 3).

**O que esta porta NÃO é.** Não é a cota diária (`UsageEventRepository`) nem o
kill switch por custo (`ServiceBudget`) — os três resolvem riscos diferentes.
Esta protege contra um cliente disparando POSTs além do que um aluno de
verdade produziria, independente de quanto cada um custa.

**Por que uma porta e não `Depends` direto no adapter.** A regra de camada
(ADR-0012) proíbe `api/` de instanciar um cliente Redis sem passar por uma
abstração testável — o mesmo motivo de toda outra porta deste projeto. A
diferença aqui é que quem CONSOME esta porta é a borda HTTP (`api/`), não
`application`: rate limit por IP não é regra de negócio, é proteção de
infraestrutura, e por isso não faz parte do `Result` do `StartTurn` como a
cota e o kill switch fazem.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from datetime import timedelta


class RateLimiter(Protocol):
    """Um contador de janela fixa, atômico por construção.

    ``hit`` registra UMA ocorrência e devolve se ela ainda cabe no limite —
    registro e verificação são a MESMA operação, nunca um ``GET`` seguido de
    ``SET`` (a corrida clássica: duas requisições leem o mesmo valor antes de
    qualquer uma escrever, e as duas passam quando só uma deveria).
    """

    async def hit(self, key: str, *, window: timedelta, limit: int) -> bool:
        """``True`` se esta ocorrência ainda está dentro do limite da janela."""
        ...
