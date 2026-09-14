"""Os seis endpoints de auth, ponta a ponta pela rota (ADR-0007, CARD-049).

**As portas de infraestrutura (repositórios, e-mail) são fakes** — a mesma
regra de todo teste de `api/` (o `lifespan` nem roda). ``PasswordHasher`` e
``AccessTokenIssuer`` são os adapters REAIS: são puros e rápidos, e é esta
suíte que prova que o fio inteiro (hash argon2id + JWT de verdade) funciona
junto, não só cada peça isolada.
"""

from __future__ import annotations

import re

from fastapi import FastAPI
from httpx import AsyncClient

from fakes_api import Fakes, wav_de
from fakes_pipeline import FakeSocialIdentityProvider
from voicecoach.api import dependencies as deps
from voicecoach.application.ports.social_identity import (
    InvalidSocialTokenError,
    VerifiedSocialIdentity,
)
from voicecoach.domain.auth import SocialProvider

REGISTRO = {"email": "novo@example.com", "password": "senha-super-segura"}
CHAVE_TURN = {"Idempotency-Key": "chave-do-teste-de-auth-0001"}


def upload(segundos: float = 2.0) -> dict[str, tuple[str, bytes, str]]:
    return {"audio": ("fala.wav", wav_de(segundos), "audio/wav")}


def url_do_token(enviados: list[tuple[str, str]]) -> str:
    _destinatario, url = enviados[0]
    token = re.search(r"token=([^&\s\"'<]+)", url)
    assert token is not None
    return token.group(1)


async def test_registro_devolve_202_e_envia_o_link(
    client: AsyncClient, fakes: Fakes
) -> None:
    resposta = await client.post("/v1/auth/register", json=REGISTRO)

    assert resposta.status_code == 202
    assert len(fakes.email_sender.enviados) == 1
    assert fakes.email_sender.enviados[0][0] == REGISTRO["email"]


async def test_registro_com_email_ja_cadastrado_devolve_a_mesma_resposta(
    client: AsyncClient, fakes: Fakes
) -> None:
    """O e-mail seedado em `Fakes.__init__` já existe — mesma resposta, sem
    reenviar (não vazar quais e-mails existem)."""
    resposta = await client.post(
        "/v1/auth/register",
        json={"email": "aluno@example.com", "password": "outra-senha-valida"},
    )

    assert resposta.status_code == 202
    assert fakes.email_sender.enviados == []


async def test_fluxo_completo_registro_confirmacao_login_refresh_logout(
    client: AsyncClient, fakes: Fakes
) -> None:
    await client.post("/v1/auth/register", json=REGISTRO)
    token = url_do_token(fakes.email_sender.enviados)

    confirmacao = await client.get(f"/v1/auth/confirm-email?token={token}")
    assert confirmacao.status_code == 200

    login = await client.post("/v1/auth/login", json=REGISTRO)
    assert login.status_code == 200
    par = login.json()
    assert par["token_type"] == "bearer"
    assert par["expires_in"] == 900

    refresh = await client.post(
        "/v1/auth/refresh", json={"refresh_token": par["refresh_token"]}
    )
    assert refresh.status_code == 200
    novo_par = refresh.json()
    assert novo_par["refresh_token"] != par["refresh_token"]

    # Reuso do refresh ANTIGO: a família inteira já está revogada.
    reuso = await client.post(
        "/v1/auth/refresh", json={"refresh_token": par["refresh_token"]}
    )
    assert reuso.status_code == 401

    # O novo par, entregue pelo refresh válido, também morreu no reuso.
    novo_tambem_morto = await client.post(
        "/v1/auth/refresh", json={"refresh_token": novo_par["refresh_token"]}
    )
    assert novo_tambem_morto.status_code == 401

    logout = await client.post(
        "/v1/auth/logout", json={"refresh_token": par["refresh_token"]}
    )
    assert logout.status_code == 204


async def test_login_com_senha_errada_e_401(client: AsyncClient, fakes: Fakes) -> None:
    await client.post("/v1/auth/register", json=REGISTRO)
    token = url_do_token(fakes.email_sender.enviados)
    await client.get(f"/v1/auth/confirm-email?token={token}")

    resposta = await client.post(
        "/v1/auth/login", json={"email": REGISTRO["email"], "password": "senha-errada"}
    )

    assert resposta.status_code == 401
    assert resposta.json()["type"] == "urn:voicecoach:problem:invalid-credentials"


async def test_confirmar_com_token_invalido_e_400(client: AsyncClient) -> None:
    resposta = await client.get("/v1/auth/confirm-email?token=nao-existe")

    assert resposta.status_code == 400


async def test_resend_confirmation_devolve_202_mesmo_para_email_inexistente(
    client: AsyncClient, fakes: Fakes
) -> None:
    resposta = await client.post(
        "/v1/auth/resend-confirmation", json={"email": "ninguem@example.com"}
    )

    assert resposta.status_code == 202
    assert fakes.email_sender.enviados == []


async def test_turn_com_email_nao_verificado_e_403(
    client: AsyncClient, fakes: Fakes
) -> None:
    """ADR-0007, item 4: login liberado, POST de turn bloqueado."""
    credencial = fakes.credentials.by_id[next(iter(fakes.credentials.by_id))]
    credencial.email_verified_at = None

    resposta = await client.post(
        f"/v1/sessions/{fakes.sessao.id}/turns", files=upload(), headers=CHAVE_TURN
    )

    assert resposta.status_code == 403
    assert resposta.json()["type"] == "urn:voicecoach:problem:email-not-verified"


async def test_turn_com_email_verificado_passa_pelo_gate(
    client: AsyncClient, fakes: Fakes
) -> None:
    """O padrão da suíte (`fakes.credentials` já vem com ALUNO verificado)."""
    resposta = await client.post(
        f"/v1/sessions/{fakes.sessao.id}/turns", files=upload(), headers=CHAVE_TURN
    )

    assert resposta.status_code == 202


async def test_fluxo_completo_de_esqueci_minha_senha(
    client: AsyncClient, fakes: Fakes
) -> None:
    await client.post("/v1/auth/register", json=REGISTRO)
    token_confirmacao = url_do_token(fakes.email_sender.enviados)
    await client.get(f"/v1/auth/confirm-email?token={token_confirmacao}")

    login = await client.post("/v1/auth/login", json=REGISTRO)
    par_antigo = login.json()

    pedido = await client.post(
        "/v1/auth/request-password-reset", json={"email": REGISTRO["email"]}
    )
    assert pedido.status_code == 202
    token_reset = url_do_token(fakes.email_sender.resets_enviados)

    nova_senha = "senha-totalmente-nova-456"
    reset = await client.post(
        "/v1/auth/reset-password",
        json={"token": token_reset, "new_password": nova_senha},
    )
    assert reset.status_code == 200

    # A senha antiga não abre mais a conta.
    login_com_senha_antiga = await client.post("/v1/auth/login", json=REGISTRO)
    assert login_com_senha_antiga.status_code == 401

    # A sessão de ANTES do reset morreu — ADR-0007, "troca de senha revoga".
    refresh_com_token_antigo = await client.post(
        "/v1/auth/refresh", json={"refresh_token": par_antigo["refresh_token"]}
    )
    assert refresh_com_token_antigo.status_code == 401

    # A senha nova funciona.
    login_com_senha_nova = await client.post(
        "/v1/auth/login",
        json={"email": REGISTRO["email"], "password": nova_senha},
    )
    assert login_com_senha_nova.status_code == 200


async def test_request_password_reset_devolve_202_mesmo_para_email_inexistente(
    client: AsyncClient, fakes: Fakes
) -> None:
    resposta = await client.post(
        "/v1/auth/request-password-reset", json={"email": "ninguem@example.com"}
    )

    assert resposta.status_code == 202
    assert fakes.email_sender.resets_enviados == []


async def test_reset_password_com_token_invalido_e_400(client: AsyncClient) -> None:
    senha_de_teste = "qualquer-coisa-123"  # gitleaks:allow -- não é segredo real
    resposta = await client.post(
        "/v1/auth/reset-password",
        json={"token": "nao-existe", "new_password": senha_de_teste},
    )

    assert resposta.status_code == 400


# -- Login social: Google e Apple (CARD-060, ADR-0070) -----------------------


def _identidade(provider: SocialProvider) -> VerifiedSocialIdentity:
    return VerifiedSocialIdentity(
        provider=provider,
        external_id=f"{provider.value}-sub-1",
        email="aluno@example.com",
        email_verified=True,
        display_name="Aluno" if provider == SocialProvider.GOOGLE else None,
    )


async def test_login_google_novo_aluno_devolve_o_par_de_tokens(
    app: FastAPI, client: AsyncClient
) -> None:
    app.dependency_overrides[deps.google_identity_provider] = lambda: (
        FakeSocialIdentityProvider(_identidade(SocialProvider.GOOGLE))
    )

    resposta = await client.post("/v1/auth/google", json={"id_token": "qualquer"})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert "access_token" in corpo
    assert "refresh_token" in corpo


async def test_login_apple_aceita_display_name_na_primeira_vez(
    app: FastAPI, client: AsyncClient
) -> None:
    app.dependency_overrides[deps.apple_identity_provider] = lambda: (
        FakeSocialIdentityProvider(_identidade(SocialProvider.APPLE))
    )

    resposta = await client.post(
        "/v1/auth/apple",
        json={"identity_token": "qualquer", "display_name": "Nome Da Apple"},
    )

    assert resposta.status_code == 200
    assert "access_token" in resposta.json()


async def test_login_google_token_invalido_e_401(
    app: FastAPI, client: AsyncClient
) -> None:
    app.dependency_overrides[deps.google_identity_provider] = lambda: (
        FakeSocialIdentityProvider(erro=InvalidSocialTokenError("assinatura ruim"))
    )

    resposta = await client.post("/v1/auth/google", json={"id_token": "adulterado"})

    assert resposta.status_code == 401
    assert resposta.json()["type"].endswith(":invalid-social-token")


async def test_login_google_sem_client_id_configurado_e_503(
    app: FastAPI, client: AsyncClient
) -> None:
    """Simula o boot real (`lifespan.py`) sem `GOOGLE_CLIENT_ID` — o card não
    pôde ser fechado sem a credencial real, e este é o desfecho documentado:
    503, nunca 500, nunca silêncio.
    """
    app.state.google_identity_provider = None

    resposta = await client.post("/v1/auth/google", json={"id_token": "qualquer"})

    assert resposta.status_code == 503
    assert resposta.json()["type"].endswith(":dependency-unavailable")
