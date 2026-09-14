"""Verificação de identidade federada — Google e Apple (CARD-060, ADR-0070).

**Uma porta, dois adapters — nunca um SDK completo de provedor.** O que
atravessa esta fronteira é sempre a mesma forma
(``VerifiedSocialIdentity``): quatro campos que sobram depois da verificação
criptográfica contra o JWKS público de cada provedor. O caso de uso
(``login_with_social.py``) nunca vê o JWT cru nem sabe que existe
`PyJWKClient` do outro lado — a mesma disciplina de ``PasswordHasher`` e
``AccessTokenIssuer`` (ADR-0007).

**Por que a porta não distingue "token expirado" de "assinatura inválida" de
"emissor errado".** Nenhum dos três é uma decisão que o caso de uso toma
diferente — os três terminam no mesmo desfecho HTTP (`401`, "entre de novo").
Distinguir aqui criaria uma união fechada que ninguém consome, só para
espelhar a granularidade que o PyJWT já expõe.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from voicecoach.domain.auth import SocialProvider


class InvalidSocialTokenError(RuntimeError):
    """O token do provedor não passou a verificação.

    Mora na porta, como ``LlmError``/``MediaStorageError``/``TurnQueueError``
    (ADR-0031, item 5): quem captura é o caso de uso, em ``application``, que
    não pode importar ``adapters`` para conhecer a exceção nativa do PyJWT
    ou do cliente JWKS.
    """


@dataclass(frozen=True, slots=True)
class VerifiedSocialIdentity:
    """O que sobra depois da verificação — nunca o token em claro.

    ``display_name`` é ``None`` quando o provedor simplesmente não carrega
    nome no token — é o caso da Apple: o `identityToken` **nunca** tem `name`
    (a Apple entrega o nome fora do JWT, só na primeira autorização, e só o
    cliente o recebe — ver o comando ``LoginWithSocial.display_name_hint``).
    O Google carrega `name` no `id_token` sempre que o escopo `profile` foi
    pedido, então o adapter do Google preenche este campo; o da Apple nunca
    preenche.
    """

    provider: SocialProvider
    external_id: str
    email: str
    email_verified: bool
    display_name: str | None


class SocialIdentityProvider(Protocol):
    """Verifica um token de identidade contra a chave pública do provedor."""

    async def verify(self, token: str) -> VerifiedSocialIdentity:
        """Levanta ``InvalidSocialTokenError`` para qualquer motivo de
        recusa — adulterado, expirado, audiência/emissor errado, ou assinado
        por uma chave que já rotacionou e saiu do JWKS. Nunca deixa a
        exceção nativa da biblioteca de verificação atravessar a porta.
        """
        ...
