"""``GoogleIdentityProvider`` contra uma chave RSA de teste (CARD-060, ADR-0070).

**Por que uma chave de teste, e não o JWKS real do Google.** O que este
adapter faz de arriscado é a verificação criptográfica (assinatura,
audiência, emissor) — isso É testável sem rede, gerando um par de chaves na
hora e assinando um token com o mesmo formato que o Google produz. O que
não é testável sem credencial real (`GOOGLE_CLIENT_ID`) é a integração
ponta a ponta contra o Google de verdade — essa parte é a dívida declarada
do CARD-060.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.exceptions import PyJWKClientError

from voicecoach.adapters.auth.google_identity_provider import GoogleIdentityProvider
from voicecoach.application.ports.social_identity import InvalidSocialTokenError
from voicecoach.domain.auth import SocialProvider

CLIENT_ID = "meu-app.apps.googleusercontent.com"


class _ChaveFalsa:
    def __init__(self, key: object) -> None:
        self.key = key


class _ClienteDeChavesFalso:
    """Satisfaz `_ClienteDeChaves` sem bater na rede — devolve sempre a
    mesma chave pública de teste, como o `PyJWKClient` faria depois do
    primeiro cache hit.
    """

    def __init__(self, public_key: object, *, erro: Exception | None = None) -> None:
        self._public_key = public_key
        self._erro = erro
        self.chamadas = 0

    def get_signing_key_from_jwt(self, token: str) -> _ChaveFalsa:
        self.chamadas += 1
        if self._erro is not None:
            raise self._erro
        return _ChaveFalsa(self._public_key)


def _par_de_chaves() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    privada = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return privada, privada.public_key()


def _token_do_google(
    privada: rsa.RSAPrivateKey,
    *,
    aud: str = CLIENT_ID,
    iss: str = "https://accounts.google.com",
    email: str = "aluno@example.com",
    email_verified: bool = True,
    sub: str = "108-google-sub",
    name: str | None = "Aluno do Google",
    exp_delta: int = 3600,
) -> str:
    agora = int(time.time())
    payload = {
        "iss": iss,
        "aud": aud,
        "sub": sub,
        "email": email,
        "email_verified": email_verified,
        "iat": agora,
        "exp": agora + exp_delta,
    }
    if name is not None:
        payload["name"] = name
    return jwt.encode(payload, privada, algorithm="RS256")


async def test_token_valido_devolve_a_identidade_verificada() -> None:
    privada, publica = _par_de_chaves()
    token = _token_do_google(privada)
    provider = GoogleIdentityProvider(
        client_id=CLIENT_ID, jwks_client=_ClienteDeChavesFalso(publica)
    )

    identidade = await provider.verify(token)

    assert identidade.provider == SocialProvider.GOOGLE
    assert identidade.external_id == "108-google-sub"
    assert identidade.email == "aluno@example.com"
    assert identidade.email_verified is True
    assert identidade.display_name == "Aluno do Google"


async def test_sem_name_display_name_e_none_e_nao_e_erro() -> None:
    """`name` só existe quando o escopo `profile` foi pedido — ausência é
    normal, ao contrário de `email`/`sub`.
    """
    privada, publica = _par_de_chaves()
    token = _token_do_google(privada, name=None)
    provider = GoogleIdentityProvider(
        client_id=CLIENT_ID, jwks_client=_ClienteDeChavesFalso(publica)
    )

    identidade = await provider.verify(token)

    assert identidade.display_name is None


async def test_assinado_com_outra_chave_e_invalido() -> None:
    """A adulteração mais direta: o token é de verdade, mas não foi ESTA
    chave privada que o assinou — a mesma classe de ataque que qualquer
    JWT de terceiro precisa recusar.
    """
    privada_do_atacante, _ = _par_de_chaves()
    _, publica_de_verdade = _par_de_chaves()
    token_adulterado = _token_do_google(privada_do_atacante)
    provider = GoogleIdentityProvider(
        client_id=CLIENT_ID, jwks_client=_ClienteDeChavesFalso(publica_de_verdade)
    )

    with pytest.raises(InvalidSocialTokenError):
        await provider.verify(token_adulterado)


async def test_audiencia_errada_e_invalido() -> None:
    """`aud` é o `client_id` — um token emitido para OUTRO app não vale
    aqui, mesmo assinado pela chave certa do Google.
    """
    privada, publica = _par_de_chaves()
    token = _token_do_google(privada, aud="outro-app.apps.googleusercontent.com")
    provider = GoogleIdentityProvider(
        client_id=CLIENT_ID, jwks_client=_ClienteDeChavesFalso(publica)
    )

    with pytest.raises(InvalidSocialTokenError):
        await provider.verify(token)


async def test_emissor_errado_e_invalido() -> None:
    privada, publica = _par_de_chaves()
    token = _token_do_google(privada, iss="https://outro-emissor.example.com")
    provider = GoogleIdentityProvider(
        client_id=CLIENT_ID, jwks_client=_ClienteDeChavesFalso(publica)
    )

    with pytest.raises(InvalidSocialTokenError):
        await provider.verify(token)


async def test_token_expirado_e_invalido() -> None:
    privada, publica = _par_de_chaves()
    token = _token_do_google(privada, exp_delta=-10)
    provider = GoogleIdentityProvider(
        client_id=CLIENT_ID, jwks_client=_ClienteDeChavesFalso(publica)
    )

    with pytest.raises(InvalidSocialTokenError):
        await provider.verify(token)


async def test_sem_email_e_invalido() -> None:
    """`email`/`sub` ausentes não são exceção nativa do PyJWT — são a
    própria checagem deste adapter, e o motivo é o mesmo: sem `email` não
    há como o caso de uso decidir criar-ou-linkar.
    """
    agora = int(time.time())
    privada, publica = _par_de_chaves()
    payload = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "sub": "108-google-sub",
        "iat": agora,
        "exp": agora + 3600,
    }
    token = jwt.encode(payload, privada, algorithm="RS256")
    provider = GoogleIdentityProvider(
        client_id=CLIENT_ID, jwks_client=_ClienteDeChavesFalso(publica)
    )

    with pytest.raises(InvalidSocialTokenError):
        await provider.verify(token)


async def test_jwks_fora_do_ar_vira_invalid_social_token_nunca_exception_crua() -> None:
    """A porta promete nunca deixar a exceção nativa da biblioteca de
    verificação atravessar — inclusive quando o problema é a BUSCA da
    chave, não o token em si.
    """
    _, publica = _par_de_chaves()
    provider = GoogleIdentityProvider(
        client_id=CLIENT_ID,
        jwks_client=_ClienteDeChavesFalso(
            publica, erro=PyJWKClientError("JWKS do Google fora do ar")
        ),
    )

    with pytest.raises(InvalidSocialTokenError):
        await provider.verify("qualquer-coisa")


def test_data_do_teste_e_2026() -> None:
    """Documenta a suposição implícita de todo `exp`/`iat` acima: o relógio
    real da máquina de CI está em 2026, não antes — se um dia isto quebrar,
    é porque a suposição deixou de valer, não porque o adapter mudou.
    """
    assert datetime.now(UTC).year >= 2026
