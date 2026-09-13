"""``ResendEmailSender`` — sem tocar rede, via ``httpx.MockTransport`` (ADR-0068)."""

from __future__ import annotations

import httpx
import pytest

from voicecoach.adapters.email.resend_email_sender import ResendEmailSender
from voicecoach.application.ports.email_sender import EmailSenderError


async def test_envia_com_o_remetente_e_a_chave_certos() -> None:
    pedidos: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        pedidos.append(request)
        return httpx.Response(200, json={"id": "abc"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    sender = ResendEmailSender(
        client=client,
        api_key="re_test_key",
        from_email="Voicecoach <onboarding@resend.dev>",
        timeout_seconds=10.0,
    )

    await sender.send_verification(
        to="aluno@example.com",
        verification_url="https://api.example.com/v1/auth/confirm-email?token=abc",
    )

    assert len(pedidos) == 1
    assert pedidos[0].headers["authorization"] == "Bearer re_test_key"
    corpo = pedidos[0].content.decode()
    assert "aluno@example.com" in corpo
    assert "onboarding@resend.dev" in corpo
    assert "token=abc" in corpo


async def test_send_password_reset_usa_assunto_e_link_proprios() -> None:
    pedidos: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        pedidos.append(request)
        return httpx.Response(200, json={"id": "abc"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    sender = ResendEmailSender(
        client=client,
        api_key="re_test_key",
        from_email="Voicecoach <onboarding@resend.dev>",
        timeout_seconds=10.0,
    )

    await sender.send_password_reset(
        to="aluno@example.com",
        reset_url="https://api.example.com/v1/auth/reset-password?token=xyz",
    )

    assert len(pedidos) == 1
    corpo = pedidos[0].content.decode()
    assert "Redefinir sua senha" in corpo
    assert "token=xyz" in corpo


async def test_4xx_vira_email_sender_error() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(401, json={"message": "chave inválida"})
        )
    )
    sender = ResendEmailSender(
        client=client,
        api_key="chave-errada",
        from_email="Voicecoach <onboarding@resend.dev>",
        timeout_seconds=10.0,
    )

    with pytest.raises(EmailSenderError):
        await sender.send_verification(
            to="aluno@example.com", verification_url="https://example.com/x"
        )


async def test_falha_de_transporte_vira_email_sender_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("recusado", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    sender = ResendEmailSender(
        client=client,
        api_key="re_test_key",
        from_email="Voicecoach <onboarding@resend.dev>",
        timeout_seconds=10.0,
    )

    with pytest.raises(EmailSenderError):
        await sender.send_verification(
            to="aluno@example.com", verification_url="https://example.com/x"
        )
