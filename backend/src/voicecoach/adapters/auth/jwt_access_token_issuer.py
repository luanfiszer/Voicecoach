"""``AccessTokenIssuer`` sobre ``PyJWT``, HS256 (ADR-0007).

**HS256 e não RS256/ES256.** Um único processo assina E valida o mesmo
token — não há um serviço separado que só *valida* sem poder assinar. A
assinatura assimétrica (RS256) resolveria um problema que este sistema não
tem (distribuir a capacidade de validar sem distribuir a de assinar), ao
custo de gerenciar um par de chaves em vez de um segredo só.

**Por que ``issue``/``decode`` são síncronos.** HMAC-SHA256 sobre um payload
de poucas dezenas de bytes é da ordem de microssegundos — nem de longe a
mesma classe de custo do ``argon2id`` (que É deliberadamente lento). Não há
``run_in_executor`` aqui pela mesma razão que a assinatura SigV4 de URL do
storage (ADR-0045) também é síncrona: nenhuma das duas bloqueia o event loop
de forma que importe.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

from voicecoach.application.ports.access_tokens import InvalidAccessTokenError

_ALGORITHM = "HS256"
# A claim que carrega a identidade. `sub` ("subject") é o nome que o RFC 7519
# reserva para exatamente este papel — usar um nome próprio (`student_id`)
# funcionaria, mas ignoraria o vocabulário que qualquer biblioteca/ferramenta
# de depuração de JWT já espera encontrar.
_CLAIM_SUBJECT = "sub"


class JwtAccessTokenIssuer:
    """Implementa ``application.ports.access_tokens.AccessTokenIssuer``."""

    def __init__(self, *, secret: str, ttl: timedelta) -> None:
        self._secret = secret
        self._ttl = ttl

    def issue(self, student_id: UUID) -> str:
        agora = datetime.now(UTC)
        payload = {
            _CLAIM_SUBJECT: str(student_id),
            "iat": agora,
            "exp": agora + self._ttl,
        }
        return jwt.encode(payload, self._secret, algorithm=_ALGORITHM)

    def decode(self, token: str) -> UUID:
        try:
            payload = jwt.decode(token, self._secret, algorithms=[_ALGORITHM])
        except jwt.InvalidTokenError as exc:
            message = f"access token inválido: {exc}"
            raise InvalidAccessTokenError(message) from exc

        bruto = payload.get(_CLAIM_SUBJECT)
        try:
            return UUID(bruto)
        except (TypeError, ValueError) as exc:
            message = f"access token com `sub` fora do formato: {bruto!r}"
            raise InvalidAccessTokenError(message) from exc
