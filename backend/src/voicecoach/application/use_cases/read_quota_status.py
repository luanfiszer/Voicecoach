"""O saldo de cota como leitura — o aluno sabe antes de bater na parede (CARD-033).

**Por que isto nunca falha.** RNF1 é literal: *"a tela que explica a parede não
pode estar atrás da parede"*. Por isso não há `Result` aqui — ao contrário do
`StartTurnHandler`, que RECUSA um turn, este caso de uso só INFORMA, e informar
nunca é um desfecho que a chamada possa errar (a única entrada é um id de
aluno, e não há "aluno não existe" nesta fase sem auth: o id é sempre
``DEV_STUDENT_ID``, resolvido pela borda).

**A mesma fonte que o freio usa** (RNF3): `usage_events.totals_for_student` e
`service_budget.is_exceeded` são exatamente as duas chamadas que
`StartTurnHandler` já faz. Se a leitura usasse outra query, "12 min restantes"
e a recusa no 11º poderiam divergir — e isso só apareceria com aluno de
verdade reclamando.

**RF5, o caso esquisito:** minutos sobrando **com** o teto de turns batido. A
tela mostra sempre os MINUTOS (RF5: "a leitura mostra só os minutos"); o motivo
do bloqueio é informado à parte, em ``blocked_reason``, com uma frase honesta
que não expõe "teto de turns" como mecânica interna
(``MANY_SHORT_TURNS`` → "você fez muitas falas curtas hoje").

**Sem cache (RNF2, resposta explícita).** As duas leituras que compõem esta
consulta já são as mesmas que todo `POST /turns` paga: uma agregação por
índice composto (CARD-014) e uma leitura Redis (ADR-0063). Nenhuma das duas é
uma varredura, e cachear introduziria uma terceira fonte para divergir da do
freio (RNF3) — o problema que o cache resolveria (custo) já está resolvido
pelo índice, e o problema que criaria (mais uma fonte) é o que o card mais
teme. TTL e gatilho, portanto: não há; a decisão é não cachear.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from typing import TYPE_CHECKING

from voicecoach.application.quota_window import janela_diaria

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime
    from uuid import UUID

    from voicecoach.application.ports.repositories import UsageEventRepository
    from voicecoach.application.ports.service_budget import ServiceBudget


class BlockedReason(StrEnum):
    """Por que o aluno não pode falar AGORA — nunca por quê em dólares (RF4).

    ``DAILY_MINUTES`` é o caso comum, e a tela já tem a barra para ele. Os
    outros dois são os que RF3/RF5 pedem para não caírem na mesma mensagem:
    ``MANY_SHORT_TURNS`` é o teto de turns mordendo com minutos sobrando, e
    ``SERVICE_PAUSED`` é o kill switch — um fato do PRODUTO, não do aluno.
    """

    DAILY_MINUTES = "daily_minutes"
    MANY_SHORT_TURNS = "many_short_turns"
    SERVICE_PAUSED = "service_paused"


@dataclass(frozen=True, slots=True)
class ReadQuotaStatus:
    student_id: UUID


@dataclass(frozen=True, slots=True)
class QuotaStatus:
    """O que a tela de perfil (artboard 12) e o chip (artboard 01) precisam.

    ``resets_at`` é o MESMO instante que o `retry_after` do 429 do CARD-015
    aponta (RNF3/RF2) — os dois nascem de `janela_diaria`.
    """

    spoken: timedelta
    quota_spoken: timedelta
    resets_at: datetime
    service_available: bool
    blocked_reason: BlockedReason | None


class ReadQuotaStatusHandler:
    def __init__(
        self,
        *,
        usage_events: UsageEventRepository,
        service_budget: ServiceBudget,
        clock: Callable[[], datetime],
        daily_quota_spoken: timedelta,
        daily_quota_turns: int,
    ) -> None:
        self._usage = usage_events
        self._budget = service_budget
        self._clock = clock
        self._daily_quota_spoken = daily_quota_spoken
        self._daily_quota_turns = daily_quota_turns

    async def handle(self, query: ReadQuotaStatus) -> QuotaStatus:
        agora = self._clock()
        inicio_do_dia, inicio_de_amanha = janela_diaria(agora)

        # As DUAS chamadas que `StartTurnHandler` faz, na MESMA ordem — não
        # importa aqui (nada é recusado), mas manter a ordem é o que deixa
        # óbvio, na leitura lado a lado, que é a mesma regra em dois lugares.
        servico_disponivel = not await self._budget.is_exceeded(when=agora)
        consumo = await self._usage.totals_for_student(
            query.student_id, since=inicio_do_dia, until=inicio_de_amanha
        )

        motivo: BlockedReason | None = None
        if not servico_disponivel:
            motivo = BlockedReason.SERVICE_PAUSED
        elif consumo.spoken >= self._daily_quota_spoken:
            motivo = BlockedReason.DAILY_MINUTES
        elif consumo.turns >= self._daily_quota_turns:
            motivo = BlockedReason.MANY_SHORT_TURNS

        return QuotaStatus(
            spoken=consumo.spoken,
            quota_spoken=self._daily_quota_spoken,
            resets_at=inicio_de_amanha,
            service_available=servico_disponivel,
            blocked_reason=motivo,
        )
