"""Porta de envio de e-mail transacional — o provedor decidido no ADR-0068.

**``EmailSenderError`` mora aqui**, mesma razão de sempre (ADR-0031, item 5):
o adapter concreto (``adapters/email/``) conhece a exceção nativa do
provedor/``httpx``; quem chama (os casos de uso de registro e reenvio) só
pode capturar algo que ``application`` tem permissão de importar.

**O desfecho de um provedor fora do ar não é ``Result``, é exceção
capturada e engolida no caso de uso** — ver
``application.use_cases.register_student``: "o cadastro conclui, o e-mail é
retentado" é requisito explícito do CARD-049, então a falha de e-mail nunca
propaga até a borda como 5xx.
"""

from __future__ import annotations

from typing import Protocol


class EmailSenderError(RuntimeError):
    """O provedor de e-mail recusou ou não respondeu."""


class EmailSender(Protocol):
    """Manda os dois e-mails transacionais que a auth precisa (ADR-0007)."""

    async def send_verification(self, *, to: str, verification_url: str) -> None: ...

    async def send_password_reset(self, *, to: str, reset_url: str) -> None: ...
