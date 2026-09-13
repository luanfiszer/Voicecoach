"""``create_email_sender`` — escolha explícita, sem fallback silencioso (ADR-0068)."""

from __future__ import annotations

import pytest

from voicecoach.adapters.email.console_email_sender import ConsoleEmailSender
from voicecoach.adapters.email.factory import (
    EmailProviderMisconfiguredError,
    create_email_sender,
)
from voicecoach.adapters.email.resend_email_sender import ResendEmailSender
from voicecoach.config import EmailProvider, Settings


def test_default_e_console_custo_zero() -> None:
    settings = Settings(  # type: ignore[call-arg]  # o pydantic preenche do ambiente
        anthropic_api_key="test-key",
        jwt_secret="test-jwt-secret-0123456789abcdef",  # gitleaks:allow
        _env_file=None,
    )

    sender = create_email_sender(settings)

    assert isinstance(sender, ConsoleEmailSender)


def test_resend_sem_chave_recusa_a_subida() -> None:
    """ADR-0027, item 3: escolha explícita incompatível levanta, nunca cai
    para o console em silêncio."""
    settings = Settings(  # type: ignore[call-arg]
        anthropic_api_key="test-key",
        jwt_secret="test-jwt-secret-0123456789abcdef",  # gitleaks:allow
        email_provider=EmailProvider.RESEND,
        _env_file=None,
    )

    with pytest.raises(EmailProviderMisconfiguredError, match="RESEND_API_KEY"):
        create_email_sender(settings)


def test_resend_com_chave_sobe() -> None:
    settings = Settings(  # type: ignore[call-arg]
        anthropic_api_key="test-key",
        jwt_secret="test-jwt-secret-0123456789abcdef",  # gitleaks:allow
        email_provider=EmailProvider.RESEND,
        resend_api_key="re_test_key",
        _env_file=None,
    )

    sender = create_email_sender(settings)

    assert isinstance(sender, ResendEmailSender)
