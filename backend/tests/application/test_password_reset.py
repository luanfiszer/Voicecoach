"""``RequestPasswordResetHandler`` e ``ResetPasswordHandler`` — o "esqueci
minha senha" que o CARD-049 nomeou como "o furo clássico" (ADR-0007).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fakes_pipeline import (
    FakeCredentialRepository,
    FakeEmailSender,
    FakePasswordHasher,
    FakePasswordResetTokenRepository,
    FakeRefreshTokenRepository,
    FakeUnitOfWork,
    RelogioFalso,
)
from voicecoach.application.result import Err, Ok
from voicecoach.application.token_hashing import hash_opaque_token, new_opaque_token
from voicecoach.application.use_cases.password_reset import (
    RequestPasswordReset,
    RequestPasswordResetHandler,
    ResetPassword,
    ResetPasswordHandler,
    ResetPasswordRejected,
)
from voicecoach.domain.auth import Credential, PasswordResetToken, RefreshToken

INICIO = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)
NOVO_ID = UUID("55555555-5555-5555-5555-555555555555")


def credencial() -> Credential:
    return Credential(
        id=uuid4(),
        student_id=uuid4(),
        email="aluno@example.com",
        password_hash="hash-antigo",
        created_at=INICIO,
    )


async def test_pedido_para_email_existente_envia_o_link() -> None:
    cred = credencial()
    credentials = FakeCredentialRepository(cred)
    reset_tokens = FakePasswordResetTokenRepository()
    sender = FakeEmailSender()
    ids = iter([NOVO_ID, uuid4()])
    handler = RequestPasswordResetHandler(
        credentials=credentials,
        reset_tokens=reset_tokens,
        email_sender=sender,
        unit_of_work=FakeUnitOfWork(),
        clock=RelogioFalso(inicio=INICIO),
        new_id=lambda: next(ids),
        reset_ttl=timedelta(hours=1),
        reset_url=lambda token: f"https://api.example.com/reset?token={token}",
    )

    await handler.handle(RequestPasswordReset(email="aluno@example.com"))

    assert len(reset_tokens.by_id) == 1
    assert len(sender.resets_enviados) == 1
    assert sender.resets_enviados[0][0] == "aluno@example.com"


async def test_pedido_com_provedor_de_email_fora_nao_propaga() -> None:
    """Mesma disciplina do registro: o token é criado, o envio pode falhar."""
    cred = credencial()
    credentials = FakeCredentialRepository(cred)
    reset_tokens = FakePasswordResetTokenRepository()
    sender = FakeEmailSender(falha=True)
    handler = RequestPasswordResetHandler(
        credentials=credentials,
        reset_tokens=reset_tokens,
        email_sender=sender,
        unit_of_work=FakeUnitOfWork(),
        clock=RelogioFalso(inicio=INICIO),
        new_id=uuid4,
        reset_ttl=timedelta(hours=1),
        reset_url=lambda token: f"https://api.example.com/reset?token={token}",
    )

    await handler.handle(RequestPasswordReset(email="aluno@example.com"))

    assert len(reset_tokens.by_id) == 1
    assert sender.resets_enviados == []


async def test_pedido_para_email_inexistente_nao_vaza_nem_falha() -> None:
    credentials = FakeCredentialRepository()
    reset_tokens = FakePasswordResetTokenRepository()
    sender = FakeEmailSender()
    handler = RequestPasswordResetHandler(
        credentials=credentials,
        reset_tokens=reset_tokens,
        email_sender=sender,
        unit_of_work=FakeUnitOfWork(),
        clock=RelogioFalso(inicio=INICIO),
        new_id=uuid4,
        reset_ttl=timedelta(hours=1),
        reset_url=lambda token: f"https://api.example.com/reset?token={token}",
    )

    await handler.handle(RequestPasswordReset(email="ninguem@example.com"))

    assert reset_tokens.by_id == {}
    assert sender.resets_enviados == []


def montar_reset(
    cred: Credential, *refresh_tokens: RefreshToken, agora: datetime = INICIO
) -> tuple[
    ResetPasswordHandler,
    FakePasswordResetTokenRepository,
    FakeCredentialRepository,
    FakeRefreshTokenRepository,
]:
    credentials = FakeCredentialRepository(cred)
    tokens = FakePasswordResetTokenRepository()
    refresh = FakeRefreshTokenRepository(*refresh_tokens)
    handler = ResetPasswordHandler(
        reset_tokens=tokens,
        credentials=credentials,
        refresh_tokens=refresh,
        hasher=FakePasswordHasher(),
        unit_of_work=FakeUnitOfWork(),
        clock=RelogioFalso(inicio=agora),
    )
    return handler, tokens, credentials, refresh


async def test_reset_com_token_valido_troca_a_senha_e_desloga_todas_as_sessoes() -> (
    None
):
    cred = credencial()
    plano, hash_ = new_opaque_token()
    token = PasswordResetToken(
        id=uuid4(),
        student_id=cred.student_id,
        token_hash=hash_,
        created_at=INICIO,
        expires_at=INICIO + timedelta(hours=1),
    )
    # Duas famílias vivas — dois aparelhos logados — e as duas têm de morrer.
    familia_a = RefreshToken(
        id=uuid4(),
        student_id=cred.student_id,
        family_id=uuid4(),
        token_hash=hash_opaque_token("token-aparelho-a"),
        created_at=INICIO,
        expires_at=INICIO + timedelta(days=30),
    )
    familia_b = RefreshToken(
        id=uuid4(),
        student_id=cred.student_id,
        family_id=uuid4(),
        token_hash=hash_opaque_token("token-aparelho-b"),
        created_at=INICIO,
        expires_at=INICIO + timedelta(days=30),
    )
    handler, tokens, credentials, refresh = montar_reset(cred, familia_a, familia_b)
    tokens.by_id[token.id] = token

    resultado = await handler.handle(
        ResetPassword(token=plano, new_password="senha-nova-123")
    )

    assert isinstance(resultado, Ok)
    assert credentials.by_id[cred.id].password_hash == "hash-de-senha-nova-123"
    assert tokens.by_id[token.id].used_at is not None
    assert all(t.revoked_at is not None for t in refresh.by_id.values())


async def test_reset_com_token_invalido_e_rejeitado_e_nao_toca_a_senha() -> None:
    cred = credencial()
    handler, _tokens, credentials, _refresh = montar_reset(cred)

    resultado = await handler.handle(
        ResetPassword(token="token-que-nao-existe", new_password="senha-nova-123")
    )

    assert isinstance(resultado, Err)
    assert isinstance(resultado.error, ResetPasswordRejected)
    assert credentials.by_id[cred.id].password_hash == "hash-antigo"


async def test_reset_com_token_expirado_e_rejeitado() -> None:
    cred = credencial()
    plano, hash_ = new_opaque_token()
    token = PasswordResetToken(
        id=uuid4(),
        student_id=cred.student_id,
        token_hash=hash_,
        created_at=INICIO,
        expires_at=INICIO + timedelta(minutes=30),
    )
    handler, tokens, credentials, _refresh = montar_reset(
        cred, agora=INICIO + timedelta(hours=2)
    )
    tokens.by_id[token.id] = token

    resultado = await handler.handle(
        ResetPassword(token=plano, new_password="senha-nova-123")
    )

    assert isinstance(resultado, Err)
    assert credentials.by_id[cred.id].password_hash == "hash-antigo"
