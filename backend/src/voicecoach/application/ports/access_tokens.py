"""Porta de emissão/leitura do access token — JWT stateless, ADR-0007.

**``InvalidAccessToken`` mora na porta, não no adapter** — mesmo princípio do
``TurnQueueError``/``MediaStorageError`` (ADR-0031, item 5): quem a captura é
a borda (``api/dependencies.py``), que não pode importar ``adapters`` para
conhecer a exceção nativa do PyJWT (``jwt.InvalidTokenError`` e suas
subclasses). Herda de ``RuntimeError`` e não de ``DomainError`` (ADR-0017):
um token forjado ou expirado não é uma invariante de agregado violada, é a
infraestrutura de auth dizendo "isto não é meu".
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from uuid import UUID


class InvalidAccessTokenError(RuntimeError):
    """Token ausente, malformado, expirado ou com assinatura inválida."""


class AccessTokenIssuer(Protocol):
    """Emite e decodifica o JWT de ~15 min que carrega ``student_id``.

    **Stateless nos dois sentidos** — não há chamada a banco nem a Redis em
    nenhum dos dois métodos. É o design do ADR-0007 (Alternativa B recusada):
    o preço aceito é até 15 min de token válido depois de uma revogação: quem
    revoga de verdade é o refresh, no banco.
    """

    def issue(self, student_id: UUID) -> str: ...

    def decode(self, token: str) -> UUID:
        """O ``student_id`` do token, ou levanta ``InvalidAccessTokenError``."""
        ...
