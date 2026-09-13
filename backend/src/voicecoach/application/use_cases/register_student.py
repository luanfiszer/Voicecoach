"""``POST /v1/auth/register`` — cadastro por e-mail+senha (ADR-0007, CARD-049).

**Por que este caso de uso não devolve ``Result``.** Não há um segundo
desfecho observável de fora: "e-mail já cadastrado" responde exatamente igual
a "conta criada" — é o próprio critério de aceite do card ("não vazar quais
e-mails existem"). Um ``Result`` com um ``Err`` que a borda nunca traduz
diferente seria tipo morto; ``handle`` devolve ``None`` porque não há nada
que o chamador precise decidir depois.

**Por que a senha é sempre hasheada, mesmo quando o e-mail já existe.** É a
outra metade do "não vazar": se o hash só rodasse no caminho de sucesso, o
tempo de resposta do endpoint distinguiria os dois casos tão bem quanto uma
mensagem de erro diferente.

**Por que a falha de e-mail não propaga.** RNF do CARD-049: "o cadastro
conclui e o e-mail é retentado — falhar o cadastro porque um terceiro caiu
perde o usuário para sempre." O aluno existe e pode pedir reenvio
(``ResendConfirmation``) mesmo que o primeiro envio tenha falhado.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from voicecoach.application.ports.email_sender import EmailSenderError
from voicecoach.application.ports.repositories import ConflictingWriteError
from voicecoach.application.token_hashing import new_opaque_token
from voicecoach.domain.auth import Credential, EmailVerificationToken
from voicecoach.domain.student import Student

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime, timedelta
    from uuid import UUID

    from voicecoach.application.ports.auth_repositories import (
        CredentialRepository,
        EmailVerificationTokenRepository,
    )
    from voicecoach.application.ports.email_sender import EmailSender
    from voicecoach.application.ports.password_hasher import PasswordHasher
    from voicecoach.application.ports.repositories import StudentRepository, UnitOfWork

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RegisterStudent:
    email: str
    password: str


class RegisterStudentHandler:
    def __init__(
        self,
        *,
        students: StudentRepository,
        credentials: CredentialRepository,
        verification_tokens: EmailVerificationTokenRepository,
        hasher: PasswordHasher,
        email_sender: EmailSender,
        unit_of_work: UnitOfWork,
        clock: Callable[[], datetime],
        new_id: Callable[[], UUID],
        verification_ttl: timedelta,
        verification_url: Callable[[str], str],
    ) -> None:
        self._students = students
        self._credentials = credentials
        self._verification_tokens = verification_tokens
        self._hasher = hasher
        self._email_sender = email_sender
        self._uow = unit_of_work
        self._clock = clock
        self._new_id = new_id
        self._verification_ttl = verification_ttl
        self._verification_url = verification_url

    async def handle(self, command: RegisterStudent) -> None:
        password_hash = await self._hasher.hash(command.password)

        existente = await self._credentials.get_by_email(command.email)
        if existente is not None:
            # Mesma resposta de um cadastro novo — a checagem existe só para
            # não duplicar Student/Credential, nunca para informar o chamador.
            return

        agora = self._clock()
        student = Student(
            id=self._new_id(),
            display_name=command.email.split("@")[0],
            created_at=agora,
        )
        credential = Credential(
            id=self._new_id(),
            student_id=student.id,
            email=command.email,
            password_hash=password_hash,
            created_at=agora,
        )
        await self._students.add(student)
        await self._credentials.add(credential)
        try:
            await self._uow.commit()
        except ConflictingWriteError:
            # Corrida: outra requisição registrou o MESMO e-mail entre o
            # `get_by_email` acima e este commit. Mesma resposta — a conta
            # dela já existe, esta chamada não cria uma segunda.
            return

        token_claro, token_hash = new_opaque_token()
        verificacao = EmailVerificationToken(
            id=self._new_id(),
            student_id=student.id,
            token_hash=token_hash,
            created_at=agora,
            expires_at=agora + self._verification_ttl,
        )
        await self._verification_tokens.add(verificacao)
        await self._uow.commit()

        try:
            await self._email_sender.send_verification(
                to=command.email,
                verification_url=self._verification_url(token_claro),
            )
        except EmailSenderError:
            logger.exception(
                "não foi possível enviar o e-mail de confirmação; "
                "a conta existe e o reenvio funciona (ResendConfirmation)"
            )
