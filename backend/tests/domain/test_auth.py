"""As invariantes de leitura de ``Credential``, ``RefreshToken`` e
``EmailVerificationToken`` (ADR-0007, CARD-049).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from voicecoach.domain.auth import (
    Credential,
    EmailVerificationToken,
    PasswordResetToken,
    RefreshToken,
)

AGORA = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)


def test_credential_nao_verificada_por_padrao() -> None:
    credencial = Credential(
        id=uuid4(),
        student_id=uuid4(),
        email="aluno@example.com",
        password_hash="hash",
        created_at=AGORA,
    )

    assert credencial.is_email_verified is False


def test_credential_verificada_apos_marcar() -> None:
    credencial = Credential(
        id=uuid4(),
        student_id=uuid4(),
        email="aluno@example.com",
        password_hash="hash",
        created_at=AGORA,
        email_verified_at=AGORA,
    )

    assert credencial.is_email_verified is True


def refresh_token(
    *, revoked_at: datetime | None = None, expires_at: datetime | None = None
) -> RefreshToken:
    return RefreshToken(
        id=uuid4(),
        student_id=uuid4(),
        family_id=uuid4(),
        token_hash="hash",
        created_at=AGORA,
        expires_at=expires_at or AGORA + timedelta(days=30),
        revoked_at=revoked_at,
    )


def test_refresh_token_usavel_quando_nao_revogado_e_dentro_do_prazo() -> None:
    assert refresh_token().is_usable(AGORA + timedelta(days=1)) is True


def test_refresh_token_revogado_nao_e_usavel() -> None:
    token = refresh_token(revoked_at=AGORA)
    assert token.is_usable(AGORA + timedelta(seconds=1)) is False


def test_refresh_token_expirado_nao_e_usavel() -> None:
    token = refresh_token(expires_at=AGORA + timedelta(days=1))
    assert token.is_usable(AGORA + timedelta(days=2)) is False


def verification_token(
    *, used_at: datetime | None = None, expires_at: datetime | None = None
) -> EmailVerificationToken:
    return EmailVerificationToken(
        id=uuid4(),
        student_id=uuid4(),
        token_hash="hash",
        created_at=AGORA,
        expires_at=expires_at or AGORA + timedelta(hours=24),
        used_at=used_at,
    )


def test_verification_token_usavel_quando_nao_usado_e_dentro_do_prazo() -> None:
    assert verification_token().is_usable(AGORA + timedelta(hours=1)) is True


def test_verification_token_ja_usado_nao_e_usavel() -> None:
    token = verification_token(used_at=AGORA)
    assert token.is_usable(AGORA + timedelta(seconds=1)) is False


def test_verification_token_expirado_nao_e_usavel() -> None:
    token = verification_token(expires_at=AGORA + timedelta(hours=1))
    assert token.is_usable(AGORA + timedelta(hours=2)) is False


def reset_token(
    *, used_at: datetime | None = None, expires_at: datetime | None = None
) -> PasswordResetToken:
    return PasswordResetToken(
        id=uuid4(),
        student_id=uuid4(),
        token_hash="hash",
        created_at=AGORA,
        expires_at=expires_at or AGORA + timedelta(hours=1),
        used_at=used_at,
    )


def test_reset_token_usavel_quando_nao_usado_e_dentro_do_prazo() -> None:
    assert reset_token().is_usable(AGORA + timedelta(minutes=30)) is True


def test_reset_token_ja_usado_nao_e_usavel() -> None:
    token = reset_token(used_at=AGORA)
    assert token.is_usable(AGORA + timedelta(seconds=1)) is False


def test_reset_token_expirado_nao_e_usavel() -> None:
    token = reset_token(expires_at=AGORA + timedelta(minutes=30))
    assert token.is_usable(AGORA + timedelta(hours=1)) is False
