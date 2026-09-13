"""A janela diária da cota — compartilhada entre o freio e a leitura (ADR-0063).

**Por que é módulo próprio, e não duplicado.** `StartTurnHandler` (CARD-015) e
`ReadQuotaStatusHandler` (CARD-033) precisam do MESMO instante de virada — se
divergirem, a tela promete "renova às 00:00" e o `retry_after` do 429 aponta
para outro instante, e é o tipo de divergência que só aparece com usuário real
(RNF3 do CARD-033).

"Hoje" é o calendário de **Brasília**, a promessa que a tela faz — não o UTC em
que o banco grava `occurred_at`. Duplicado (não importado) do fuso do adapter
`redis_service_budget` de propósito: `application` não importa `adapters`
(ADR-0013), e uma constante de fuso não justifica um módulo `domain` novo só
para ser compartilhada entre as duas.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from datetime import datetime

FUSO_DA_COTA = ZoneInfo("America/Sao_Paulo")


def janela_diaria(agora: datetime) -> tuple[datetime, datetime]:
    """``[meia-noite de hoje, meia-noite de amanhã)`` no fuso da cota.

    Meio-aberta como o `totals_for_student` exige — e como todo o resto do
    projeto que soma por janela (ADR-0051).
    """
    inicio = agora.astimezone(FUSO_DA_COTA).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return inicio, inicio + timedelta(days=1)
