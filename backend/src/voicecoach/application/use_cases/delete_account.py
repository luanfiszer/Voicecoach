"""``DELETE /v1/students/me`` — a exclusão lógica e imediata (CARD-051, ADR-0069).

**O que este caso de uso faz, e o que não faz.** Ele marca a conta e mata
toda sessão viva — o suficiente para que "não consegue mais entrar,
imediatamente" (o primeiro critério de aceite do card) seja verdade ao fim
deste `handle`. O que ele **não** faz é apagar nada: nem o áudio no S3, nem
as linhas de `turns`/`sessions`, nem a própria linha de `Student`. Isso é
trabalho do expurgo físico, assíncrono, em
``purge_deleted_accounts.PurgeDeletedAccountsHandler`` — a mesma separação
que o ADR-0069 registra como a decisão central do card.

**Por que não é `Result`.** Não há um segundo desfecho observável: quem
chega aqui já passou por ``requesting_student_id``, que já garantiu que a
conta existe e está ativa NO INÍCIO desta mesma requisição. Não há
"e-mail não existe" nem "senha errada" para distinguir — só há "aconteceu".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime
    from uuid import UUID

    from voicecoach.application.ports.auth_repositories import RefreshTokenRepository
    from voicecoach.application.ports.repositories import StudentRepository, UnitOfWork


@dataclass(frozen=True, slots=True)
class DeleteAccount:
    student_id: UUID


class DeleteAccountHandler:
    def __init__(
        self,
        *,
        students: StudentRepository,
        refresh_tokens: RefreshTokenRepository,
        unit_of_work: UnitOfWork,
        clock: Callable[[], datetime],
    ) -> None:
        self._students = students
        self._refresh_tokens = refresh_tokens
        self._uow = unit_of_work
        self._clock = clock

    async def handle(self, command: DeleteAccount) -> None:
        agora = self._clock()
        # Marcar antes de revogar: se o processo morrer entre os dois
        # `UPDATE`s, a próxima tentativa (ou a varredura de expurgo, que
        # também revoga implicitamente ao apagar `refresh_tokens` em
        # cascata quando o `Student` finalmente sai) ainda encontra a
        # conta marcada — nunca o contrário (tokens revogados, conta
        # "ativa").
        await self._students.mark_deleted(command.student_id, agora)
        await self._refresh_tokens.revoke_all_for_student(command.student_id, agora)
        await self._uow.commit()
