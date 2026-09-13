"""``LoginStudentHandler`` — o par de tokens, ou a mesma recusa para os dois
casos que não deveriam se distinguir (ADR-0007, CARD-049).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fakes_pipeline import (
    FakeAccessTokenIssuer,
    FakeCredentialRepository,
    FakePasswordHasher,
    FakeRefreshTokenRepository,
    FakeUnitOfWork,
    RelogioFalso,
)
from voicecoach.application.result import Err, Ok
from voicecoach.application.use_cases.login_student import (
    InvalidCredentials,
    LoginStudent,
    LoginStudentHandler,
)
from voicecoach.domain.auth import Credential

INICIO = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)
NOVO_ID = UUID("22222222-2222-2222-2222-222222222222")


def montar(
    credencial: Credential | None,
) -> tuple[
    LoginStudentHandler,
    FakeRefreshTokenRepository,
    FakePasswordHasher,
    FakeAccessTokenIssuer,
    FakeUnitOfWork,
]:
    credentials = FakeCredentialRepository(*([credencial] if credencial else []))
    refresh_tokens = FakeRefreshTokenRepository()
    hasher = FakePasswordHasher()
    issuer = FakeAccessTokenIssuer()
    uow = FakeUnitOfWork()
    ids = iter([NOVO_ID, uuid4(), uuid4()])
    handler = LoginStudentHandler(
        credentials=credentials,
        refresh_tokens=refresh_tokens,
        hasher=hasher,
        token_issuer=issuer,
        unit_of_work=uow,
        clock=RelogioFalso(inicio=INICIO),
        new_id=lambda: next(ids),
        access_token_ttl=timedelta(minutes=15),
        refresh_token_ttl=timedelta(days=30),
    )
    return handler, refresh_tokens, hasher, issuer, uow


def credencial_valida() -> Credential:
    return Credential(
        id=uuid4(),
        student_id=uuid4(),
        email="aluno@example.com",
        password_hash="hash-de-senha-certa",
        created_at=INICIO,
    )


async def test_credenciais_corretas_emitem_o_par_de_tokens() -> None:
    credencial = credencial_valida()
    handler, refresh_tokens, _hasher, issuer, uow = montar(credencial)

    resultado = await handler.handle(
        LoginStudent(email="aluno@example.com", password="senha-certa")
    )

    assert isinstance(resultado, Ok)
    par = resultado.value
    assert par.access_token == f"access-token-para-{credencial.student_id}"
    assert par.expires_in_seconds == 900
    assert len(refresh_tokens.by_id) == 1
    assert issuer.emitidos == [credencial.student_id]
    assert uow.commits == 1


async def test_senha_errada_e_invalid_credentials() -> None:
    handler, refresh_tokens, hasher, _issuer, uow = montar(credencial_valida())

    resultado = await handler.handle(
        LoginStudent(email="aluno@example.com", password="senha-errada")
    )

    assert isinstance(resultado, Err)
    assert isinstance(resultado.error, InvalidCredentials)
    assert refresh_tokens.by_id == {}
    assert uow.commits == 0
    assert hasher.chamadas_de_verify == 1


async def test_email_inexistente_e_invalid_credentials_e_verify_roda_assim_mesmo() -> (
    None
):
    """A checagem de tempo constante do card: `verify` roda mesmo sem credencial."""
    handler, _refresh_tokens, hasher, _issuer, _uow = montar(None)

    resultado = await handler.handle(
        LoginStudent(email="ninguem@example.com", password="qualquer-coisa")
    )

    assert isinstance(resultado, Err)
    assert isinstance(resultado.error, InvalidCredentials)
    assert hasher.chamadas_de_verify == 1
