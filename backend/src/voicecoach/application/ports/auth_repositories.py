"""Portas de persistência da auth (ADR-0007, CARD-049).

Separadas de ``repositories.py`` pela mesma razão que pôs ``Translation`` fora
do ``TurnRepository`` (ADR-0051): três entidades que nenhum consumidor do
resto do sistema (worker, varreduras, SSE) precisa conhecer. Juntá-las ao
arquivo de repositórios existentes inflaria o import de todo mundo que só
queria ``TurnRepository``.

Mesma disciplina das outras portas: ``Protocol`` estrutural, sem ``update``
genérico — cada mutação é um método nomeado pelo que ela representa no
negócio (``mark_email_verified``, não ``save``), a mesma regra que
``SessionRepository.try_end`` já segue.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from voicecoach.domain.auth import (
        Credential,
        EmailVerificationToken,
        PasswordResetToken,
        RefreshToken,
        SocialIdentity,
        SocialProvider,
    )


class CredentialRepository(Protocol):
    """Acesso a e-mail+senha de um ``Student``."""

    async def add(self, credential: Credential) -> None: ...

    async def get_by_email(self, email: str) -> Credential | None: ...

    async def get_by_student_id(self, student_id: UUID) -> Credential | None: ...

    async def mark_email_verified(self, student_id: UUID, when: datetime) -> None:
        """Marca verificado pelo ``student_id``, não pelo id da credencial.

        Todo chamador (``ConfirmEmailHandler``) só tem o ``student_id`` à mão
        — é o que o ``EmailVerificationToken`` carrega. Pedir o id da
        credencial obrigaria uma consulta extra só para descobri-lo, e
        ``student_id`` já é único em ``credentials`` (uma credencial por
        aluno).
        """
        ...

    async def update_password_hash(self, student_id: UUID, password_hash: str) -> None:
        """Troca o hash de senha — só o ``ResetPasswordHandler`` chama isto."""
        ...


class RefreshTokenRepository(Protocol):
    """Acesso aos elos de refresh — a metade *stateful* e revogável do par.

    ``revoke_family`` é o método que implementa a detecção de reuso do
    ADR-0007: apresentar um token já rotacionado revoga TODOS os elos vivos
    daquela família, não só o apresentado.
    """

    async def add(self, token: RefreshToken) -> None: ...

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None: ...

    async def mark_revoked(self, token_id: UUID, when: datetime) -> None: ...

    async def revoke_family(self, family_id: UUID, when: datetime) -> None: ...

    async def revoke_all_for_student(self, student_id: UUID, when: datetime) -> None:
        """Revoga TODAS as famílias do aluno — troca de senha desloga tudo
        (ADR-0007: "logout/troca de senha revogam"). Diferente de
        ``revoke_family``: um aluno pode ter uma família por aparelho
        logado, e resetar a senha precisa acabar com todas de uma vez, não
        só a da sessão que pediu o reset.
        """
        ...


class EmailVerificationTokenRepository(Protocol):
    """Acesso aos links de confirmação de e-mail, de uso único."""

    async def add(self, token: EmailVerificationToken) -> None: ...

    async def get_by_hash(self, token_hash: str) -> EmailVerificationToken | None: ...

    async def mark_used(self, token_id: UUID, when: datetime) -> None: ...


class PasswordResetTokenRepository(Protocol):
    """Acesso aos links de "esqueci minha senha", de uso único."""

    async def add(self, token: PasswordResetToken) -> None: ...

    async def get_by_hash(self, token_hash: str) -> PasswordResetToken | None: ...

    async def mark_used(self, token_id: UUID, when: datetime) -> None: ...


class SocialIdentityRepository(Protocol):
    """Acesso aos vínculos de identidade federada (CARD-060, ADR-0070)."""

    async def add(self, identity: SocialIdentity) -> None: ...

    async def get_by_provider(
        self, provider: SocialProvider, external_id: str
    ) -> SocialIdentity | None:
        """A busca que decide "já vi esta pessoa" — pela chave do provedor,
        nunca pelo e-mail (ver o docstring de `SocialIdentity`).
        """
        ...
