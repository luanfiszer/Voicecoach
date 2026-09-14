"""Verifica o `id_token` do Google contra o JWKS público (CARD-060, ADR-0070).

**`PyJWKClient`, não o SDK `google-auth`.** O SDK completo (`google-auth` +
`google-auth-oauthlib`) traz um cliente HTTP próprio e uma superfície bem
maior do que "verificar um JWT contra uma chave pública que já roda em
produção para o nosso próprio access token" (ADR-0007). `PyJWT` já é
dependência; `PyJWKClient` é a mesma biblioteca buscando e cacheando o JWKS
— nenhuma dependência nova pesada, e simetria com o adapter da Apple, que
teria de fazer o mesmo à mão de qualquer forma (não existe SDK oficial da
Apple em Python).

**Por que a busca da chave passa por um executor.** `PyJWKClient` é
síncrono por dentro (usa `urllib` para buscar o JWKS) — a mesma classe de
problema do `boto3` no adapter de storage (ADR-0034): uma chamada de rede
que nunca cede o controle trava o event loop inteiro enquanto dura. Ele
CACHEIA a chave (a rotação é rara), então isto roda raramente depois do
primeiro login — mas "raro" não é "nunca", e o primeiro login de cada
processo paga o custo cheio.
"""

from __future__ import annotations

import asyncio
from typing import Any, Protocol

import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientError

from voicecoach.application.ports.social_identity import (
    InvalidSocialTokenError,
    VerifiedSocialIdentity,
)
from voicecoach.domain.auth import SocialProvider

# Os dois emissores que o Google usa em produção (verificado no próprio
# id_token: `iss` varia entre os dois, sem aviso — aceitar só um rejeitaria
# tokens válidos de metade dos clientes, de forma imprevisível para quem
# depura).
_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
_ISSUERS = ("https://accounts.google.com", "accounts.google.com")
_ALGORITHM = "RS256"


class _ChaveDeAssinatura(Protocol):
    """O subconjunto de `jwt.PyJWK` que este adapter lê: a chave pública
    pronta para `jwt.decode`. Protocol, e não o `PyJWK` concreto, para que
    um teste possa satisfazer isto com um objeto qualquer com `.key` — sem
    precisar montar um `PyJWK` de verdade a partir de um JWKS de teste.
    """

    key: Any


class _ClienteDeChaves(Protocol):
    """O subconjunto de `PyJWKClient` que este adapter consome — o que torna
    o adapter testável com uma chave de teste, sem bater no Google de
    verdade."""

    def get_signing_key_from_jwt(self, token: str) -> _ChaveDeAssinatura: ...


class GoogleIdentityProvider:
    """Implementa `application.ports.social_identity.SocialIdentityProvider`."""

    provider = SocialProvider.GOOGLE

    def __init__(
        self, *, client_id: str, jwks_client: _ClienteDeChaves | None = None
    ) -> None:
        self._client_id = client_id
        self._jwks_client = jwks_client or PyJWKClient(_JWKS_URL)

    async def verify(self, token: str) -> VerifiedSocialIdentity:
        loop = asyncio.get_running_loop()
        try:
            chave = await loop.run_in_executor(
                None, self._jwks_client.get_signing_key_from_jwt, token
            )
            claims = jwt.decode(
                token,
                chave.key,
                algorithms=[_ALGORITHM],
                audience=self._client_id,
                issuer=list(_ISSUERS),
            )
        except (jwt.exceptions.PyJWTError, PyJWKClientError) as exc:
            message = f"id_token do Google inválido: {exc}"
            raise InvalidSocialTokenError(message) from exc

        email = claims.get("email")
        sub = claims.get("sub")
        if not email or not sub:
            message = "id_token do Google sem `email` ou `sub`"
            raise InvalidSocialTokenError(message)

        return VerifiedSocialIdentity(
            provider=self.provider,
            external_id=sub,
            email=email,
            email_verified=bool(claims.get("email_verified", False)),
            # `name` só existe quando o escopo `profile` foi pedido no
            # cliente — ausência é normal, não erro (ao contrário de
            # `email`/`sub`, que o Google sempre inclui).
            display_name=claims.get("name"),
        )
