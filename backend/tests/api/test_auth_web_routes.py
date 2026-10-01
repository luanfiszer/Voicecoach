"""As rotas de sessão da web: refresh em cookie `HttpOnly` (CARD-064, ADR-0077).

O client deste arquivo fala `https://` de propósito: o cookie é `Secure`, e o
cookie jar do httpx (como o do navegador) não devolve cookie `Secure` por
HTTP puro. Um teste por `http://` passaria a ver "sessão expirada" onde o
navegador de verdade funcionaria.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from fakes_api import Fakes
from fakes_pipeline import FakeSocialIdentityProvider
from voicecoach.api import dependencies as deps
from voicecoach.api.routes.auth_web import REFRESH_COOKIE
from voicecoach.application.ports.social_identity import VerifiedSocialIdentity
from voicecoach.domain.auth import SocialProvider

REGISTRO = {"email": "web@example.com", "password": "senha-super-segura"}


@pytest.fixture
async def navegador(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Um client com cookie jar, como uma aba do navegador."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as cliente:
        yield cliente


async def _conta_confirmada(navegador: AsyncClient, fakes: Fakes) -> None:
    await navegador.post("/v1/auth/register", json=REGISTRO)
    _destinatario, url = fakes.email_sender.enviados[0]
    token = re.search(r"token=([^&\s\"'<]+)", url)
    assert token is not None
    await navegador.get(f"/v1/auth/confirm-email?token={token.group(1)}")


async def test_login_web_nao_poe_o_refresh_no_corpo_so_no_cookie_httponly(
    navegador: AsyncClient, fakes: Fakes
) -> None:
    """O critério de segurança do ADR-0077: o JavaScript da página nunca vê o
    refresh — ele não está no corpo, e o cookie é `HttpOnly`.
    """
    await _conta_confirmada(navegador, fakes)

    resposta = await navegador.post("/v1/auth/web/login", json=REGISTRO)

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert "refresh_token" not in corpo
    assert corpo["access_token"]
    cookie = resposta.headers["set-cookie"]
    assert cookie.startswith(f"{REFRESH_COOKIE}=")
    for atributo in ("HttpOnly", "Secure", "SameSite=strict", "Path=/v1/auth/web"):
        assert atributo.lower() in cookie.lower()


async def test_refresh_web_rotaciona_pelo_cookie_e_o_antigo_vira_reuso(
    navegador: AsyncClient, fakes: Fakes
) -> None:
    await _conta_confirmada(navegador, fakes)
    await navegador.post("/v1/auth/web/login", json=REGISTRO)
    antigo = navegador.cookies[REFRESH_COOKIE]

    renovado = await navegador.post("/v1/auth/web/refresh")

    assert renovado.status_code == 200
    assert navegador.cookies[REFRESH_COOKIE] != antigo

    # Outra "aba" que ainda tivesse o cookie antigo: reuso, a família morre.
    navegador.cookies.set(REFRESH_COOKIE, antigo, path="/v1/auth/web")
    reuso = await navegador.post("/v1/auth/web/refresh")
    assert reuso.status_code == 401


async def test_refresh_web_sem_cookie_e_401(navegador: AsyncClient) -> None:
    resposta = await navegador.post("/v1/auth/web/refresh")

    assert resposta.status_code == 401
    assert resposta.json()["type"].endswith(":invalid-refresh-token")


async def test_logout_web_revoga_e_apaga_o_cookie(
    navegador: AsyncClient, fakes: Fakes
) -> None:
    await _conta_confirmada(navegador, fakes)
    await navegador.post("/v1/auth/web/login", json=REGISTRO)
    cookie = navegador.cookies[REFRESH_COOKIE]

    saida = await navegador.post("/v1/auth/web/logout")

    assert saida.status_code == 204
    assert REFRESH_COOKIE not in navegador.cookies
    # O token que estava no cookie também morreu no servidor.
    navegador.cookies.set(REFRESH_COOKIE, cookie, path="/v1/auth/web")
    assert (await navegador.post("/v1/auth/web/refresh")).status_code == 401


async def test_login_google_web_abre_sessao_com_cookie(
    app: FastAPI, navegador: AsyncClient
) -> None:
    app.dependency_overrides[deps.google_identity_provider] = lambda: (
        FakeSocialIdentityProvider(
            VerifiedSocialIdentity(
                provider=SocialProvider.GOOGLE,
                external_id="google-sub-web",
                email="web-google@example.com",
                email_verified=True,
                display_name="Aluno Web",
            )
        )
    )

    resposta = await navegador.post("/v1/auth/web/google", json={"id_token": "x"})

    assert resposta.status_code == 200
    assert "refresh_token" not in resposta.json()
    assert REFRESH_COOKIE in navegador.cookies


async def test_as_rotas_do_mobile_continuam_devolvendo_o_par_no_corpo(
    navegador: AsyncClient, fakes: Fakes
) -> None:
    """ADR-0008: o contrato do mobile não muda — aditivo só."""
    await _conta_confirmada(navegador, fakes)

    resposta = await navegador.post("/v1/auth/login", json=REGISTRO)

    assert "refresh_token" in resposta.json()
    assert REFRESH_COOKIE not in navegador.cookies
