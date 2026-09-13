"""O expurgo físico do delete de conta — a outra metade do CARD-051, ADR-0069.

**Por que varredura periódica, e não um job por conta enfileirado no
`arq`.** O problema (idempotência, coordenação entre réplicas via `job_id`
determinístico do `cron_jobs`, lote limitado para não competir com o
`MAX_JOBS` do worker) já estava resolvido e testado por
``sweep_stale_turns``/``sweep_inactive_sessions`` (CARD-025/034). Nenhuma
característica do expurgo de conta pede um mecanismo diferente — decidir
reaproveitar em vez de desenhar de novo é a decisão técnica que o ADR-0069
registra.

**A ordem dentro de uma conta é a garantia central, não um detalhe.**

1. Apagar `turns` (cascateia correção/trecho/tradução — `usage_events`
   fica de fora, por desenho: o ADR-0069 removeu a FK de `turn_id`).
2. Apagar `sessions` — só depois, porque `turns.session_id` não tem
   `ON DELETE CASCADE`.
3. Apagar o storage (`delete_prefix`), que é a etapa que pode falhar de
   verdade (rede, MinIO fora) e é retentável por construção (apagar um
   prefixo vazio de novo é sucesso, zero objetos).
4. Só então apagar o `Student` — e é este `DELETE`, via `ON DELETE SET NULL`
   da migration, quem anonimiza qualquer `usage_events` que tenha sobrado.

Se o passo 3 falhar, os passos 1-2 já comitaram — não é um problema:
reexecutar 1-2 numa conta sem turns/sessions é `DELETE` de zero linhas,
sucesso. A conta continua marcada e inacessível (o critério de aceite do
card) até o storage responder.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from voicecoach.application.ports.media_storage import MediaStorageError
from voicecoach.domain.media_keys import student_prefix

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from voicecoach.application.ports.media_storage import MediaStorage
    from voicecoach.application.ports.repositories import (
        SessionRepository,
        StudentRepository,
        TurnRepository,
        UnitOfWork,
    )

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PurgeDeletedAccounts:
    """Sem campos — o prazo e o lote são configuração do handler, como no
    CARD-034: quem dispara (o `cron_job`) não decide quanto a rodada apaga.
    """


@dataclass(frozen=True, slots=True)
class AccountPurgeReport:
    """O que a rodada fez — log e teste, não produto."""

    examinadas: int
    expurgadas: int
    falharam_no_storage: int


class PurgeDeletedAccountsHandler:
    def __init__(
        self,
        *,
        students: StudentRepository,
        sessions: SessionRepository,
        turns: TurnRepository,
        storage: MediaStorage,
        unit_of_work: UnitOfWork,
        clock: Callable[[], datetime],
        batch_limit: int,
    ) -> None:
        self._students = students
        self._sessions = sessions
        self._turns = turns
        self._storage = storage
        self._uow = unit_of_work
        self._clock = clock
        self._batch_limit = batch_limit

    async def handle(self, command: PurgeDeletedAccounts) -> AccountPurgeReport:
        del command
        ids = await self._students.list_pending_purge(limit=self._batch_limit)

        expurgadas = falharam = 0
        for student_id in ids:
            await self._turns.delete_all_for_student(student_id)
            await self._sessions.delete_all_for_student(student_id)
            await self._uow.commit()

            try:
                await self._storage.delete_prefix(student_prefix(student_id))
            except MediaStorageError:
                # O aluno nunca vê esta falha — para ele já acabou (a conta
                # está marcada desde o `DeleteAccountHandler`). A conta
                # segue marcada, e a próxima rodada tenta de novo: turns e
                # sessions já não existem, o `delete_prefix` é quem retenta
                # de verdade.
                logger.warning(
                    "expurgo de conta %s: storage falhou, conta segue "
                    "marcada para a próxima rodada",
                    student_id,
                    exc_info=True,
                )
                falharam += 1
                continue

            await self._students.delete(student_id)
            await self._uow.commit()
            expurgadas += 1

        if ids:
            logger.info(
                "expurgo de contas: %d examinadas, %d expurgadas, %d falharam "
                "no storage",
                len(ids),
                expurgadas,
                falharam,
            )
        return AccountPurgeReport(
            examinadas=len(ids), expurgadas=expurgadas, falharam_no_storage=falharam
        )
