"""``ConfirmEmailHandler`` e ``ResendConfirmationHandler`` (ADR-0007, CARD-049)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fakes_pipeline import (
    FakeCredentialRepository,
    FakeEmailSender,
    FakeEmailVerificationTokenRepository,
    FakeUnitOfWork,
    RelogioFalso,
)
from voicecoach.application.result import Err, Ok
from voicecoach.application.token_hashing import new_opaque_token
from voicecoach.application.use_cases.email_verification import (
    ConfirmEmail,
    ConfirmEmailHandler,
    ConfirmEmailRejected,
    ResendConfirmation,
    ResendConfirmationHandler,
)
from voicecoach.domain.auth import Credential, EmailVerificationToken

INICIO = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)
NOVO_ID = UUID("44444444-4444-4444-4444-444444444444")


def credencial_nao_verificada() -> Credential:
    return Credential(
        id=uuid4(),
        student_id=uuid4(),
        email="aluno@example.com",
        password_hash="hash",
        created_at=INICIO,
    )


async def test_confirmar_com_token_valido_marca_o_email_verificado() -> None:
    credencial = credencial_nao_verificada()
    plano, hash_ = new_opaque_token()
    token = EmailVerificationToken(
        id=uuid4(),
        student_id=credencial.student_id,
        token_hash=hash_,
        created_at=INICIO,
        expires_at=INICIO + timedelta(hours=24),
    )
    tokens = FakeEmailVerificationTokenRepository(token)
    credentials = FakeCredentialRepository(credencial)
    uow = FakeUnitOfWork()
    handler = ConfirmEmailHandler(
        verification_tokens=tokens,
        credentials=credentials,
        unit_of_work=uow,
        clock=RelogioFalso(inicio=INICIO + timedelta(hours=1)),
    )

    resultado = await handler.handle(ConfirmEmail(token=plano))

    assert isinstance(resultado, Ok)
    assert credentials.by_id[credencial.id].is_email_verified is True
    assert tokens.by_id[token.id].used_at is not None
    assert uow.commits == 1


async def test_confirmar_com_token_expirado_e_rejeitado() -> None:
    credencial = credencial_nao_verificada()
    plano, hash_ = new_opaque_token()
    token = EmailVerificationToken(
        id=uuid4(),
        student_id=credencial.student_id,
        token_hash=hash_,
        created_at=INICIO,
        expires_at=INICIO + timedelta(hours=1),
    )
    tokens = FakeEmailVerificationTokenRepository(token)
    credentials = FakeCredentialRepository(credencial)
    uow = FakeUnitOfWork()
    handler = ConfirmEmailHandler(
        verification_tokens=tokens,
        credentials=credentials,
        unit_of_work=uow,
        clock=RelogioFalso(inicio=INICIO + timedelta(hours=2)),
    )

    resultado = await handler.handle(ConfirmEmail(token=plano))

    assert isinstance(resultado, Err)
    assert isinstance(resultado.error, ConfirmEmailRejected)
    assert credentials.by_id[credencial.id].is_email_verified is False
    assert uow.commits == 0


async def test_confirmar_token_ja_usado_e_rejeitado() -> None:
    credencial = credencial_nao_verificada()
    plano, hash_ = new_opaque_token()
    token = EmailVerificationToken(
        id=uuid4(),
        student_id=credencial.student_id,
        token_hash=hash_,
        created_at=INICIO,
        expires_at=INICIO + timedelta(hours=24),
        used_at=INICIO + timedelta(minutes=5),
    )
    tokens = FakeEmailVerificationTokenRepository(token)
    credentials = FakeCredentialRepository(credencial)
    handler = ConfirmEmailHandler(
        verification_tokens=tokens,
        credentials=credentials,
        unit_of_work=FakeUnitOfWork(),
        clock=RelogioFalso(inicio=INICIO + timedelta(hours=1)),
    )

    resultado = await handler.handle(ConfirmEmail(token=plano))

    assert isinstance(resultado, Err)


def montar_resend(
    credencial: Credential | None, *, email_falha: bool = False
) -> tuple[
    ResendConfirmationHandler, FakeEmailVerificationTokenRepository, FakeEmailSender
]:
    credentials = FakeCredentialRepository(*([credencial] if credencial else []))
    tokens = FakeEmailVerificationTokenRepository()
    sender = FakeEmailSender(falha=email_falha)
    ids = iter([NOVO_ID, uuid4()])
    handler = ResendConfirmationHandler(
        credentials=credentials,
        verification_tokens=tokens,
        email_sender=sender,
        unit_of_work=FakeUnitOfWork(),
        clock=RelogioFalso(inicio=INICIO),
        new_id=lambda: next(ids),
        verification_ttl=timedelta(hours=24),
        verification_url=lambda token: f"https://api.example.com/confirm?token={token}",
    )
    return handler, tokens, sender


async def test_reenvio_para_email_nao_verificado_manda_link_novo() -> None:
    credencial = credencial_nao_verificada()
    handler, tokens, sender = montar_resend(credencial)

    await handler.handle(ResendConfirmation(email="aluno@example.com"))

    assert len(tokens.by_id) == 1
    assert len(sender.enviados) == 1


async def test_reenvio_para_email_ja_verificado_nao_faz_nada() -> None:
    credencial = credencial_nao_verificada()
    credencial.email_verified_at = INICIO
    handler, tokens, sender = montar_resend(credencial)

    await handler.handle(ResendConfirmation(email="aluno@example.com"))

    assert tokens.by_id == {}
    assert sender.enviados == []


async def test_reenvio_para_email_inexistente_nao_vaza_nem_falha() -> None:
    handler, tokens, sender = montar_resend(None)

    await handler.handle(ResendConfirmation(email="ninguem@example.com"))

    assert tokens.by_id == {}
    assert sender.enviados == []


async def test_reenvio_com_provedor_fora_nao_propaga() -> None:
    """Mesma disciplina do registro: o token é criado, o envio pode falhar."""
    credencial = credencial_nao_verificada()
    handler, tokens, sender = montar_resend(credencial, email_falha=True)

    await handler.handle(ResendConfirmation(email="aluno@example.com"))

    assert len(tokens.by_id) == 1
    assert sender.enviados == []
