"""``RefreshTokensHandler`` — rotação com detecção de reuso (ADR-0007, CARD-049).

O critério de aceite mais caro do card: apresentar um refresh já rotacionado
revoga a família inteira, e todo access que sair dela morre no vencimento.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fakes_pipeline import (
    FakeAccessTokenIssuer,
    FakeRefreshTokenRepository,
    FakeUnitOfWork,
    RelogioFalso,
)
from voicecoach.application.result import Err, Ok
from voicecoach.application.token_hashing import hash_opaque_token, new_opaque_token
from voicecoach.application.use_cases.refresh_tokens import (
    RefreshRejected,
    RefreshTokens,
    RefreshTokensHandler,
)
from voicecoach.domain.auth import RefreshToken

INICIO = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)
ALUNO = uuid4()
FAMILIA = uuid4()
NOVO_ID = UUID("33333333-3333-3333-3333-333333333333")


def montar(
    *tokens: RefreshToken, inicio: datetime = INICIO
) -> tuple[RefreshTokensHandler, FakeRefreshTokenRepository, FakeUnitOfWork]:
    refresh_tokens = FakeRefreshTokenRepository(*tokens)
    uow = FakeUnitOfWork()
    ids = iter([NOVO_ID, uuid4(), uuid4(), uuid4()])
    handler = RefreshTokensHandler(
        refresh_tokens=refresh_tokens,
        token_issuer=FakeAccessTokenIssuer(),
        unit_of_work=uow,
        clock=RelogioFalso(inicio=inicio),
        new_id=lambda: next(ids),
        access_token_ttl=timedelta(minutes=15),
        refresh_token_ttl=timedelta(days=30),
    )
    return handler, refresh_tokens, uow


def token_vivo(*, plano: str, revoked_at: datetime | None = None) -> RefreshToken:
    return RefreshToken(
        id=uuid4(),
        student_id=ALUNO,
        family_id=FAMILIA,
        token_hash=hash_opaque_token(plano),
        created_at=INICIO,
        expires_at=INICIO + timedelta(days=30),
        revoked_at=revoked_at,
    )


async def test_refresh_valido_rotaciona_e_o_antigo_fica_revogado() -> None:
    plano, _hash = new_opaque_token()
    original = token_vivo(plano=plano)
    handler, refresh_tokens, uow = montar(original)

    resultado = await handler.handle(RefreshTokens(refresh_token=plano))

    assert isinstance(resultado, Ok)
    assert refresh_tokens.by_id[original.id].revoked_at is not None
    novos = [t for t in refresh_tokens.by_id.values() if t.id != original.id]
    assert len(novos) == 1
    assert novos[0].family_id == FAMILIA
    assert novos[0].revoked_at is None
    assert uow.commits == 1


async def test_reuso_de_token_ja_rotacionado_revoga_a_familia_inteira() -> None:
    """O coração do card: apresentar o token velho de novo mata todo mundo."""
    plano, _hash = new_opaque_token()
    original = token_vivo(plano=plano)
    handler, refresh_tokens, uow = montar(original)

    # Primeiro refresh: rotina normal.
    primeiro = await handler.handle(RefreshTokens(refresh_token=plano))
    assert isinstance(primeiro, Ok)

    # Reuso: o token ORIGINAL (já revogado) é apresentado de novo.
    segundo = await handler.handle(RefreshTokens(refresh_token=plano))

    assert isinstance(segundo, Err)
    assert isinstance(segundo.error, RefreshRejected)
    # TODA a família — incluindo o elo novo que o primeiro refresh emitiu —
    # está revogada. Nenhum token desta família pode mais renovar.
    assert all(t.revoked_at is not None for t in refresh_tokens.by_id.values())
    assert uow.commits == 2  # o primeiro refresh + a revogação em massa


async def test_token_desconhecido_e_rejeitado() -> None:
    handler, _refresh_tokens, uow = montar()

    resultado = await handler.handle(
        RefreshTokens(refresh_token="token-que-nao-existe")
    )

    assert isinstance(resultado, Err)
    assert isinstance(resultado.error, RefreshRejected)
    assert uow.commits == 0


async def test_token_expirado_e_rejeitado_sem_rotacionar() -> None:
    plano, _hash = new_opaque_token()
    expirado = RefreshToken(
        id=uuid4(),
        student_id=ALUNO,
        family_id=FAMILIA,
        token_hash=hash_opaque_token(plano),
        created_at=INICIO - timedelta(days=31),
        expires_at=INICIO - timedelta(days=1),
    )
    handler, refresh_tokens, uow = montar(expirado)

    resultado = await handler.handle(RefreshTokens(refresh_token=plano))

    assert isinstance(resultado, Err)
    assert isinstance(resultado.error, RefreshRejected)
    assert len(refresh_tokens.by_id) == 1
    assert uow.commits == 0
