"""``GET /v1/auth/confirm-email`` e ``POST /v1/auth/resend-confirmation`` (ADR-0007).

Os dois casos de uso vivem juntos porque compartilham a mesma entidade
(``EmailVerificationToken``) e a mesma disciplina de não vazar informação:
confirmar um token inválido e reenviar para um e-mail que não existe
respondem, cada um, sempre da mesma forma — o card já resolveu essa simetria
para o registro (``RegisterStudentHandler``), e aqui é a mesma regra.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from voicecoach.application.ports.email_sender import EmailSenderError
from voicecoach.application.result import Err, Ok, Result
from voicecoach.application.token_hashing import hash_opaque_token, new_opaque_token
from voicecoach.domain.auth import EmailVerificationToken

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime, timedelta
    from uuid import UUID

    from voicecoach.application.ports.auth_repositories import (
        CredentialRepository,
        EmailVerificationTokenRepository,
    )
    from voicecoach.application.ports.email_sender import EmailSender
    from voicecoach.application.ports.repositories import UnitOfWork

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ConfirmEmail:
    token: str


@dataclass(frozen=True, slots=True)
class ConfirmEmailRejected:
    """Token inexistente, já usado, ou expirado — uma resposta só."""


class ConfirmEmailHandler:
    def __init__(
        self,
        *,
        verification_tokens: EmailVerificationTokenRepository,
        credentials: CredentialRepository,
        unit_of_work: UnitOfWork,
        clock: Callable[[], datetime],
    ) -> None:
        self._verification_tokens = verification_tokens
        self._credentials = credentials
        self._uow = unit_of_work
        self._clock = clock

    async def handle(self, command: ConfirmEmail) -> Result[None, ConfirmEmailRejected]:
        token_hash = hash_opaque_token(command.token)
        existente = await self._verification_tokens.get_by_hash(token_hash)
        agora = self._clock()

        if existente is None or not existente.is_usable(agora):
            return Err(ConfirmEmailRejected())

        await self._verification_tokens.mark_used(existente.id, agora)
        await self._credentials.mark_email_verified(existente.student_id, agora)
        await self._uow.commit()
        return Ok(None)


@dataclass(frozen=True, slots=True)
class ResendConfirmation:
    email: str


class ResendConfirmationHandler:
    def __init__(
        self,
        *,
        credentials: CredentialRepository,
        verification_tokens: EmailVerificationTokenRepository,
        email_sender: EmailSender,
        unit_of_work: UnitOfWork,
        clock: Callable[[], datetime],
        new_id: Callable[[], UUID],
        verification_ttl: timedelta,
        verification_url: Callable[[str], str],
    ) -> None:
        self._credentials = credentials
        self._verification_tokens = verification_tokens
        self._email_sender = email_sender
        self._uow = unit_of_work
        self._clock = clock
        self._new_id = new_id
        self._verification_ttl = verification_ttl
        self._verification_url = verification_url

    async def handle(self, command: ResendConfirmation) -> None:
        credential = await self._credentials.get_by_email(command.email)
        # Mesma resposta (nenhuma) para: e-mail não existe, e-mail já
        # verificado. Reenviar para quem já confirmou não tem efeito nenhum
        # que o aluno precise ver — e recusar de forma visível revelaria
        # que o e-mail existe.
        if credential is None or credential.is_email_verified:
            return

        agora = self._clock()
        token_claro, token_hash = new_opaque_token()
        token = EmailVerificationToken(
            id=self._new_id(),
            student_id=credential.student_id,
            token_hash=token_hash,
            created_at=agora,
            expires_at=agora + self._verification_ttl,
        )
        await self._verification_tokens.add(token)
        await self._uow.commit()

        try:
            await self._email_sender.send_verification(
                to=command.email,
                verification_url=self._verification_url(token_claro),
            )
        except EmailSenderError:
            logger.exception(
                "reenvio de confirmação falhou; o aluno pode pedir de novo"
            )
