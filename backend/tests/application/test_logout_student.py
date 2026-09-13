"""``LogoutStudentHandler`` — idempotente, como ``EndSessionHandler`` (CARD-049)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fakes_pipeline import FakeRefreshTokenRepository, FakeUnitOfWork, RelogioFalso
from voicecoach.application.token_hashing import hash_opaque_token, new_opaque_token
from voicecoach.application.use_cases.logout_student import (
    LogoutStudent,
    LogoutStudentHandler,
)
from voicecoach.domain.auth import RefreshToken

INICIO = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)


def montar(
    *tokens: RefreshToken,
) -> tuple[LogoutStudentHandler, FakeRefreshTokenRepository, FakeUnitOfWork]:
    refresh_tokens = FakeRefreshTokenRepository(*tokens)
    uow = FakeUnitOfWork()
    handler = LogoutStudentHandler(
        refresh_tokens=refresh_tokens,
        unit_of_work=uow,
        clock=RelogioFalso(inicio=INICIO),
    )
    return handler, refresh_tokens, uow


async def test_logout_revoga_a_familia_inteira() -> None:
    familia = uuid4()
    plano, hash_ = new_opaque_token()
    token = RefreshToken(
        id=uuid4(),
        student_id=uuid4(),
        family_id=familia,
        token_hash=hash_,
        created_at=INICIO,
        expires_at=INICIO + timedelta(days=30),
    )
    irmao = RefreshToken(
        id=uuid4(),
        student_id=token.student_id,
        family_id=familia,
        token_hash=hash_opaque_token("outro-token-da-mesma-familia"),
        created_at=INICIO,
        expires_at=INICIO + timedelta(days=30),
    )
    handler, refresh_tokens, uow = montar(token, irmao)

    await handler.handle(LogoutStudent(refresh_token=plano))

    assert refresh_tokens.by_id[token.id].revoked_at is not None
    assert refresh_tokens.by_id[irmao.id].revoked_at is not None
    assert uow.commits == 1


async def test_logout_com_token_desconhecido_nao_falha() -> None:
    handler, _refresh_tokens, uow = montar()

    await handler.handle(LogoutStudent(refresh_token="token-que-nunca-existiu"))

    assert uow.commits == 0
