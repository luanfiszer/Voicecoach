"""``POST /v1/auth/request-password-reset`` e ``POST /v1/auth/reset-password``
(ADR-0007, CARD-049) — "o furo clássico" que o card nomeou por escrito.

Mesma disciplina de não vazar do resto do módulo: pedir reset para um e-mail
inexistente responde igual a pedir para um que existe.

**Trocar a senha revoga toda sessão** (ADR-0007: "logout/troca de senha
revogam") — ``ResetPasswordHandler`` chama
``RefreshTokenRepository.revoke_all_for_student``, não só a família de quem
está resetando. Um atacante que tenha roubado um refresh token de outro
aparelho perde o acesso no instante em que o dono redefine a senha.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from voicecoach.application.ports.email_sender import EmailSenderError
from voicecoach.application.result import Err, Ok, Result
from voicecoach.application.token_hashing import hash_opaque_token, new_opaque_token
from voicecoach.domain.auth import PasswordResetToken

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime, timedelta
    from uuid import UUID

    from voicecoach.application.ports.auth_repositories import (
        CredentialRepository,
        PasswordResetTokenRepository,
        RefreshTokenRepository,
    )
    from voicecoach.application.ports.email_sender import EmailSender
    from voicecoach.application.ports.password_hasher import PasswordHasher
    from voicecoach.application.ports.repositories import UnitOfWork

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RequestPasswordReset:
    email: str


class RequestPasswordResetHandler:
    def __init__(
        self,
        *,
        credentials: CredentialRepository,
        reset_tokens: PasswordResetTokenRepository,
        email_sender: EmailSender,
        unit_of_work: UnitOfWork,
        clock: Callable[[], datetime],
        new_id: Callable[[], UUID],
        reset_ttl: timedelta,
        reset_url: Callable[[str], str],
    ) -> None:
        self._credentials = credentials
        self._reset_tokens = reset_tokens
        self._email_sender = email_sender
        self._uow = unit_of_work
        self._clock = clock
        self._new_id = new_id
        self._reset_ttl = reset_ttl
        self._reset_url = reset_url

    async def handle(self, command: RequestPasswordReset) -> None:
        credential = await self._credentials.get_by_email(command.email)
        if credential is None:
            # Mesma resposta de um pedido para um e-mail existente — não
            # vazar quais e-mails têm conta.
            return

        agora = self._clock()
        token_claro, token_hash = new_opaque_token()
        token = PasswordResetToken(
            id=self._new_id(),
            student_id=credential.student_id,
            token_hash=token_hash,
            created_at=agora,
            expires_at=agora + self._reset_ttl,
        )
        await self._reset_tokens.add(token)
        await self._uow.commit()

        try:
            await self._email_sender.send_password_reset(
                to=command.email, reset_url=self._reset_url(token_claro)
            )
        except EmailSenderError:
            logger.exception(
                "não foi possível enviar o e-mail de redefinição de senha; "
                "o aluno pode pedir de novo"
            )


@dataclass(frozen=True, slots=True)
class ResetPassword:
    token: str
    new_password: str


@dataclass(frozen=True, slots=True)
class ResetPasswordRejected:
    """Token inexistente, já usado, ou expirado — uma resposta só."""


class ResetPasswordHandler:
    def __init__(
        self,
        *,
        reset_tokens: PasswordResetTokenRepository,
        credentials: CredentialRepository,
        refresh_tokens: RefreshTokenRepository,
        hasher: PasswordHasher,
        unit_of_work: UnitOfWork,
        clock: Callable[[], datetime],
    ) -> None:
        self._reset_tokens = reset_tokens
        self._credentials = credentials
        self._refresh_tokens = refresh_tokens
        self._hasher = hasher
        self._uow = unit_of_work
        self._clock = clock

    async def handle(
        self, command: ResetPassword
    ) -> Result[None, ResetPasswordRejected]:
        token_hash = hash_opaque_token(command.token)
        existente = await self._reset_tokens.get_by_hash(token_hash)
        agora = self._clock()

        if existente is None or not existente.is_usable(agora):
            return Err(ResetPasswordRejected())

        novo_hash = await self._hasher.hash(command.new_password)
        await self._credentials.update_password_hash(existente.student_id, novo_hash)
        await self._reset_tokens.mark_used(existente.id, agora)
        # ADR-0007: troca de senha revoga TODA sessão, não só a de quem
        # resetou — um refresh roubado de outro aparelho morre aqui.
        await self._refresh_tokens.revoke_all_for_student(existente.student_id, agora)
        await self._uow.commit()
        return Ok(None)
