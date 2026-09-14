"""Verifica o `identityToken` da Apple contra o JWKS público (CARD-060, ADR-0070).

**Mesma forma do adapter do Google** (`PyJWKClient`, executor, JWKS público)
— a Apple não publica SDK oficial em Python, então seria código próprio de
qualquer forma; a simetria com o Google não é escolha estética, é a mesma
solução aplicada duas vezes.

**O que este token NUNCA carrega: o nome.** Ao contrário do Google, o
`identityToken` da Apple não tem claim de nome em NENHUMA autorização — a
Apple entrega o nome fora do JWT, no objeto `ASAuthorizationAppleIDCredential`
do lado do cliente, e só na PRIMEIRA autorização. É por isso que
`VerifiedSocialIdentity.display_name` deste adapter é sempre `None`, e por
que `LoginWithSocial.display_name_hint` existe: o cliente precisa mandar o
nome separado, capturado naquele instante único, ou ele se perde para
sempre (o risco que o próprio card nomeia).

**`email_verified` e `is_private_email` chegam como STRING** (`"true"`/
`"false"`), não booleano — comportamento documentado da Apple, não
inconsistência do PyJWT. Um `bool(claims.get(...))` ingênuo leria a STRING
`"false"` como verdadeira (toda string não vazia é truthy em Python) — o
tipo de bug que não aparece em teste com dado bem-comportado e aparece
exatamente quando o campo vem `"false"` de verdade.
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

_JWKS_URL = "https://appleid.apple.com/auth/keys"
_ISSUER = "https://appleid.apple.com"
_ALGORITHM = "RS256"


class _ChaveDeAssinatura(Protocol):
    """Ver o docstring do gêmeo em `google_identity_provider.py` — mesmo
    motivo, mesma forma.
    """

    key: Any


class _ClienteDeChaves(Protocol):
    def get_signing_key_from_jwt(self, token: str) -> _ChaveDeAssinatura: ...


def _claim_booleana(valor: object) -> bool:
    """A Apple manda `"true"`/`"false"` como STRING nestas duas claims —
    documentado por ela, não um formato que este código escolheu. Um
    booleano de verdade (o Google manda) também é aceito, para o adapter não
    quebrar se a Apple um dia corrigir isto silenciosamente.
    """
    if isinstance(valor, bool):
        return valor
    return str(valor).strip().lower() == "true"


class AppleIdentityProvider:
    """Implementa `application.ports.social_identity.SocialIdentityProvider`."""

    provider = SocialProvider.APPLE

    def __init__(
        self, *, client_id: str, jwks_client: _ClienteDeChaves | None = None
    ) -> None:
        # `client_id` aqui é o Services ID da Apple (`com.voicecoach.web` ou
        # similar), NUNCA o bundle id do app iOS — os dois são conceitos
        # diferentes no fluxo da Apple, e confundi-los produz um `aud`
        # sempre errado, indistinguível de "token adulterado" no sintoma.
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
                issuer=_ISSUER,
            )
        except (jwt.exceptions.PyJWTError, PyJWKClientError) as exc:
            message = f"identityToken da Apple inválido: {exc}"
            raise InvalidSocialTokenError(message) from exc

        email = claims.get("email")
        sub = claims.get("sub")
        if not email or not sub:
            message = "identityToken da Apple sem `email` ou `sub`"
            raise InvalidSocialTokenError(message)

        return VerifiedSocialIdentity(
            provider=self.provider,
            external_id=sub,
            email=email,
            email_verified=_claim_booleana(claims.get("email_verified", False)),
            # Nunca vem no token — ver o docstring do módulo.
            display_name=None,
        )
