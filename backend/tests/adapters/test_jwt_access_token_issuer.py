"""``JwtAccessTokenIssuer`` — o access token stateless (ADR-0007, CARD-049)."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import jwt
import pytest

from voicecoach.adapters.auth.jwt_access_token_issuer import JwtAccessTokenIssuer
from voicecoach.application.ports.access_tokens import InvalidAccessTokenError

# Fixture de teste, não segredo real — o gitleaks (heurística genérica de alta
# entropia) marcaria cada ocorrência sem o comentário.
SEGREDO = "segredo-de-teste-com-32-bytes-ok"  # gitleaks:allow


def test_issue_e_decode_fazem_roundtrip() -> None:
    issuer = JwtAccessTokenIssuer(secret=SEGREDO, ttl=timedelta(minutes=15))
    student_id = uuid4()

    token = issuer.issue(student_id)

    assert issuer.decode(token) == student_id


def test_token_assinado_com_outro_segredo_e_invalido() -> None:
    issuer_a = JwtAccessTokenIssuer(secret="segredo-a", ttl=timedelta(minutes=15))
    issuer_b = JwtAccessTokenIssuer(secret="segredo-b", ttl=timedelta(minutes=15))
    token = issuer_a.issue(uuid4())

    with pytest.raises(InvalidAccessTokenError):
        issuer_b.decode(token)


def test_token_expirado_e_invalido() -> None:
    issuer = JwtAccessTokenIssuer(secret=SEGREDO, ttl=timedelta(seconds=-1))
    token = issuer.issue(uuid4())

    with pytest.raises(InvalidAccessTokenError):
        issuer.decode(token)


def test_token_com_sub_fora_do_formato_uuid_e_invalido() -> None:
    issuer = JwtAccessTokenIssuer(secret=SEGREDO, ttl=timedelta(minutes=15))
    token_alheio = jwt.encode({"sub": "isto-nao-e-um-uuid"}, SEGREDO, algorithm="HS256")

    with pytest.raises(InvalidAccessTokenError):
        issuer.decode(token_alheio)


def test_lixo_nao_e_jwt_e_invalido() -> None:
    issuer = JwtAccessTokenIssuer(secret=SEGREDO, ttl=timedelta(minutes=15))

    with pytest.raises(InvalidAccessTokenError):
        issuer.decode("isto.nao.e-um-jwt")
