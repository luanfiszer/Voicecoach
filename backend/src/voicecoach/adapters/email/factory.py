"""Escolha do adapter de e-mail no boot (ADR-0068).

Mesmo desenho do ``adapters/stt/factory.py`` (ADR-0027, item 3): a escolha é
**explícita** e uma configuração incompatível **levanta na subida**, nunca
cai em silêncio para o adapter de console — pedir ``resend`` sem chave e
"funcionar" mandando e-mail para o log seria uma regressão de produto
disfarçada de sucesso.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from voicecoach.config import EmailProvider

if TYPE_CHECKING:
    from voicecoach.application.ports.email_sender import EmailSender
    from voicecoach.config import Settings

logger = logging.getLogger(__name__)


class EmailProviderMisconfiguredError(RuntimeError):
    """``EMAIL_PROVIDER=resend`` sem ``RESEND_API_KEY`` — configuração impossível."""


def create_email_sender(settings: Settings) -> EmailSender:
    if settings.email_provider is EmailProvider.CONSOLE:
        from voicecoach.adapters.email.console_email_sender import ConsoleEmailSender

        logger.info("e-mail: adapter de console (custo zero, ver ADR-0068)")
        return ConsoleEmailSender()

    if settings.resend_api_key is None:
        raise EmailProviderMisconfiguredError(
            "EMAIL_PROVIDER=resend exige RESEND_API_KEY no ambiente. "
            "Sem ela, o adapter não sobe — nunca cai para o console em silêncio."
        )

    import httpx

    from voicecoach.adapters.email.resend_email_sender import ResendEmailSender

    logger.info("e-mail: adapter Resend, from=%s", settings.resend_from_email)
    return ResendEmailSender(
        client=httpx.AsyncClient(),
        api_key=settings.resend_api_key,
        from_email=settings.resend_from_email,
        timeout_seconds=settings.email_timeout_seconds,
    )
