"""``EmailSender`` sobre a API REST do Resend (ADR-0068).

**Por que ``httpx`` direto e não o SDK oficial ``resend``.** A API é um
``POST`` só, com três campos (``from``, ``to``, ``html``) e um cabeçalho de
autorização — o SDK adicionaria uma dependência inteira para embrulhar uma
chamada que ``httpx`` (já presente no projeto) faz em dez linhas. O mesmo
raciocínio que descartou ``python-jose`` em favor do ``PyJWT`` puro.

**Client injetado, nunca criado aqui dentro** — mesmo padrão do
``criarCliente`` do TypeScript e do resto dos adapters HTTP deste backend: um
``httpx.AsyncClient`` com ``transport=httpx.MockTransport(...)`` é o dublê de
teste, sem precisar de rede nem de biblioteca de mock.

**Timeout e retry (CARD-026): nunca requisição crua.** Uma tentativa, com
teto explícito — mais curto que o do professor porque isto não está no
caminho da voz do aluno; está no caminho de um e-mail que, se falhar, o
``ResendConfirmation`` já sabe reenviar.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from voicecoach.application.ports.email_sender import EmailSenderError

if TYPE_CHECKING:
    import httpx

_RESEND_API_URL = "https://api.resend.com/emails"


class ResendEmailSender:
    """Implementa ``application.ports.email_sender.EmailSender``."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        api_key: str,
        from_email: str,
        timeout_seconds: float,
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._from_email = from_email
        self._timeout = timeout_seconds

    async def send_verification(self, *, to: str, verification_url: str) -> None:
        await self._send(
            to=to,
            subject="Confirme seu e-mail — Voicecoach",
            html=(
                f"<p>Toque no link para confirmar sua conta: "
                f'<a href="{verification_url}">{verification_url}</a></p>'
            ),
        )

    async def send_password_reset(self, *, to: str, reset_url: str) -> None:
        await self._send(
            to=to,
            subject="Redefinir sua senha — Voicecoach",
            html=(
                f"<p>Toque no link para escolher uma senha nova: "
                f'<a href="{reset_url}">{reset_url}</a></p>'
                f"<p>Se você não pediu isto, ignore este e-mail.</p>"
            ),
        )

    async def _send(self, *, to: str, subject: str, html: str) -> None:
        corpo = {
            "from": self._from_email,
            "to": [to],
            "subject": subject,
            "html": html,
        }
        try:
            resposta = await self._client.post(
                _RESEND_API_URL,
                json=corpo,
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=self._timeout,
            )
        except Exception as exc:
            message = f"Resend não respondeu: {exc}"
            raise EmailSenderError(message) from exc

        if resposta.status_code >= 400:
            message = f"Resend recusou o envio: HTTP {resposta.status_code}"
            raise EmailSenderError(message)
