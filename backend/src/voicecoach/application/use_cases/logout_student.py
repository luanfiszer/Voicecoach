"""``POST /v1/auth/logout`` — revoga a família do refresh apresentado (ADR-0007).

**Sempre ``Ok``, mesmo com token desconhecido.** Deslogar um token que já não
existe (expirado, ou de outra sessão já encerrada) não é erro do chamador —
é o mesmo "não faz mal" do ``EndSessionHandler`` (CARD-031): logout é
idempotente por natureza, chamar duas vezes tem o mesmo efeito de chamar uma.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from voicecoach.application.token_hashing import hash_opaque_token

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from voicecoach.application.ports.auth_repositories import RefreshTokenRepository
    from voicecoach.application.ports.repositories import UnitOfWork


@dataclass(frozen=True, slots=True)
class LogoutStudent:
    refresh_token: str


class LogoutStudentHandler:
    def __init__(
        self,
        *,
        refresh_tokens: RefreshTokenRepository,
        unit_of_work: UnitOfWork,
        clock: Callable[[], datetime],
    ) -> None:
        self._refresh_tokens = refresh_tokens
        self._uow = unit_of_work
        self._clock = clock

    async def handle(self, command: LogoutStudent) -> None:
        token_hash = hash_opaque_token(command.refresh_token)
        existente = await self._refresh_tokens.get_by_hash(token_hash)
        if existente is not None:
            await self._refresh_tokens.revoke_family(existente.family_id, self._clock())
            await self._uow.commit()
