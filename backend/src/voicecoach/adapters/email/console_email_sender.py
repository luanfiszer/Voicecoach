"""``EmailSender`` que escreve no log — o default de custo zero (ADR-0068).

Quem lê o link de verificação em desenvolvimento é o próprio desenvolvedor,
no terminal. Nenhuma conta de terceiro, nenhum segredo, nenhuma chamada de
rede — o mesmo raciocínio que fez o STT/TTS locais serem o default do
ADR-0011.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class ConsoleEmailSender:
    """Implementa ``application.ports.email_sender.EmailSender``."""

    async def send_verification(self, *, to: str, verification_url: str) -> None:
        logger.info(
            "[email/console] confirmação de e-mail para %s: %s", to, verification_url
        )

    async def send_password_reset(self, *, to: str, reset_url: str) -> None:
        logger.info("[email/console] redefinição de senha para %s: %s", to, reset_url)
