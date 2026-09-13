"""``DeleteAccountHandler`` — a exclusão lógica e imediata (CARD-051, ADR-0069).

O que este handler faz é pouco de propósito: marcar a conta e revogar toda
sessão viva. O expurgo físico é outro caso de uso
(``purge_deleted_accounts``), testado em arquivo próprio.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fakes_pipeline import (
    FakeRefreshTokenRepository,
    FakeStudentRepository,
    FakeUnitOfWork,
    RelogioFalso,
)
from voicecoach.application.token_hashing import new_opaque_token
from voicecoach.application.use_cases.delete_account import (
    DeleteAccount,
    DeleteAccountHandler,
)
from voicecoach.domain.auth import RefreshToken
from voicecoach.domain.student import Student

INICIO = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)


async def test_marca_a_conta_e_revoga_toda_sessao_viva() -> None:
    aluno = Student(id=uuid4(), display_name="Aluno", created_at=INICIO)
    students = FakeStudentRepository(aluno)
    _, hash_a = new_opaque_token()
    _, hash_b = new_opaque_token()
    token_a = RefreshToken(
        id=uuid4(),
        student_id=aluno.id,
        family_id=uuid4(),
        token_hash=hash_a,
        created_at=INICIO,
        expires_at=INICIO + timedelta(days=30),
    )
    token_b = RefreshToken(
        id=uuid4(),
        student_id=aluno.id,
        family_id=uuid4(),  # família diferente: outro aparelho logado
        token_hash=hash_b,
        created_at=INICIO,
        expires_at=INICIO + timedelta(days=30),
    )
    refresh_tokens = FakeRefreshTokenRepository(token_a, token_b)
    uow = FakeUnitOfWork()
    handler = DeleteAccountHandler(
        students=students,
        refresh_tokens=refresh_tokens,
        unit_of_work=uow,
        clock=RelogioFalso(inicio=INICIO),
    )

    await handler.handle(DeleteAccount(student_id=aluno.id))

    assert aluno.deleted_at == INICIO
    assert not aluno.is_active
    assert refresh_tokens.by_id[token_a.id].revoked_at == INICIO
    assert refresh_tokens.by_id[token_b.id].revoked_at == INICIO
    assert uow.commits == 1


async def test_e_idempotente_preserva_o_primeiro_instante_da_exclusao() -> None:
    aluno = Student(id=uuid4(), display_name="Aluno", created_at=INICIO)
    students = FakeStudentRepository(aluno)

    handler = DeleteAccountHandler(
        students=students,
        refresh_tokens=FakeRefreshTokenRepository(),
        unit_of_work=FakeUnitOfWork(),
        clock=RelogioFalso(inicio=INICIO),
    )

    await handler.handle(DeleteAccount(student_id=aluno.id))
    primeiro_instante = aluno.deleted_at
    await handler.handle(DeleteAccount(student_id=aluno.id))

    assert aluno.deleted_at == primeiro_instante
