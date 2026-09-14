"""``AppleIdentityProvider`` contra uma chave RSA de teste (CARD-060, ADR-0070).

Mesma disciplina do gêmeo do Google — ver o docstring daquele arquivo. O que
é específico da Apple, e por isso tem teste próprio aqui: `email_verified`
chegando como STRING (`"true"`/`"false"`), e `display_name` sendo sempre
`None` porque o `identityToken` nunca carrega nome.
"""

from __future__ import annotations

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from voicecoach.adapters.auth.apple_identity_provider import AppleIdentityProvider
from voicecoach.application.ports.social_identity import InvalidSocialTokenError
from voicecoach.domain.auth import SocialProvider

CLIENT_ID = "com.voicecoach.web"  # o Services ID — nunca o bundle id do app


class _ChaveFalsa:
    def __init__(self, key: object) -> None:
        self.key = key


class _ClienteDeChavesFalso:
    def __init__(self, public_key: object) -> None:
        self._public_key = public_key

    def get_signing_key_from_jwt(self, token: str) -> _ChaveFalsa:
        return _ChaveFalsa(self._public_key)


def _par_de_chaves() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    privada = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return privada, privada.public_key()


def _token_da_apple(
    privada: rsa.RSAPrivateKey,
    *,
    email_verified: object = "true",
    is_private_email: object = "false",
    email: str = "aluno@privaterelay.appleid.com",
    sub: str = "001-apple-sub",
) -> str:
    """``email_verified``/``is_private_email`` como STRING por padrão — é
    assim que a Apple manda de verdade, não uma escolha deste teste.
    """
    agora = int(time.time())
    payload = {
        "iss": "https://appleid.apple.com",
        "aud": CLIENT_ID,
        "sub": sub,
        "email": email,
        "email_verified": email_verified,
        "is_private_email": is_private_email,
        "iat": agora,
        "exp": agora + 3600,
    }
    return jwt.encode(payload, privada, algorithm="RS256")


async def test_email_verified_como_string_true_e_lido_como_verdadeiro() -> None:
    privada, publica = _par_de_chaves()
    token = _token_da_apple(privada, email_verified="true")
    provider = AppleIdentityProvider(
        client_id=CLIENT_ID, jwks_client=_ClienteDeChavesFalso(publica)
    )

    identidade = await provider.verify(token)

    assert identidade.email_verified is True


async def test_email_verified_como_string_false_e_lido_como_falso() -> None:
    """O bug que um `bool()` ingênuo cometeria: `bool("false")` é `True` em
    Python, porque toda string não vazia é truthy. Este é o teste que
    provaria a regressão se `_claim_booleana` fosse trocado por `bool()`.
    """
    privada, publica = _par_de_chaves()
    token = _token_da_apple(privada, email_verified="false")
    provider = AppleIdentityProvider(
        client_id=CLIENT_ID, jwks_client=_ClienteDeChavesFalso(publica)
    )

    identidade = await provider.verify(token)

    assert identidade.email_verified is False


async def test_email_verified_booleano_de_verdade_tambem_funciona() -> None:
    """Se a Apple um dia corrigir o formato sem avisar, o adapter não quebra."""
    privada, publica = _par_de_chaves()
    token = _token_da_apple(privada, email_verified=True)
    provider = AppleIdentityProvider(
        client_id=CLIENT_ID, jwks_client=_ClienteDeChavesFalso(publica)
    )

    identidade = await provider.verify(token)

    assert identidade.email_verified is True


async def test_display_name_e_sempre_none() -> None:
    """O `identityToken` nunca carrega nome — não há campo `name` nem para
    testar a ausência dele ficando `None`; é `None` sempre, por construção.
    """
    privada, publica = _par_de_chaves()
    token = _token_da_apple(privada)
    provider = AppleIdentityProvider(
        client_id=CLIENT_ID, jwks_client=_ClienteDeChavesFalso(publica)
    )

    identidade = await provider.verify(token)

    assert identidade.display_name is None
    assert identidade.provider == SocialProvider.APPLE
    assert identidade.external_id == "001-apple-sub"


async def test_audiencia_errada_e_invalido() -> None:
    """O erro mais fácil de cometer integrando a Apple: `aud` é o Services
    ID, não o bundle id do app iOS — os dois têm o MESMO sintoma de erro
    aqui (token "adulterado"), documentado no docstring do adapter.
    """
    privada, publica = _par_de_chaves()
    token = _token_da_apple(privada)
    provider = AppleIdentityProvider(
        client_id="com.voicecoach.ios.bundle-id-errado",  # nunca é o aud certo
        jwks_client=_ClienteDeChavesFalso(publica),
    )

    with pytest.raises(InvalidSocialTokenError):
        await provider.verify(token)


async def test_assinado_com_outra_chave_e_invalido() -> None:
    privada_do_atacante, _ = _par_de_chaves()
    _, publica_de_verdade = _par_de_chaves()
    token_adulterado = _token_da_apple(privada_do_atacante)
    provider = AppleIdentityProvider(
        client_id=CLIENT_ID, jwks_client=_ClienteDeChavesFalso(publica_de_verdade)
    )

    with pytest.raises(InvalidSocialTokenError):
        await provider.verify(token_adulterado)


async def test_sem_email_e_invalido() -> None:
    agora = int(time.time())
    privada, publica = _par_de_chaves()
    payload = {
        "iss": "https://appleid.apple.com",
        "aud": CLIENT_ID,
        "sub": "001-apple-sub",
        "iat": agora,
        "exp": agora + 3600,
    }
    token = jwt.encode(payload, privada, algorithm="RS256")
    provider = AppleIdentityProvider(
        client_id=CLIENT_ID, jwks_client=_ClienteDeChavesFalso(publica)
    )

    with pytest.raises(InvalidSocialTokenError):
        await provider.verify(token)
