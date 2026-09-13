"""``POST /v1/auth/refresh`` — rotação com detecção de reuso (ADR-0007).

**O coração do card.** Cada chamada bem-sucedida revoga o elo apresentado e
grava um elo novo com o MESMO ``family_id``. Se um elo já revogado for
apresentado de novo — sinal de que alguém copiou um refresh token que já foi
usado e substituído —, a família inteira é revogada: todo access token que
sair dela morre no próprio prazo de 15 min, sem chance de renovar.

**Por que ``RefreshRejected`` é um caso só, sem distinguir "não existe" de
"reuso detectado" de "expirado".** Do lado de fora os três merecem a mesma
reação do cliente (voltar para a tela de login) — diferenciar na resposta
HTTP daria a um atacante um oráculo sobre qual dos três aconteceu.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from voicecoach.application.result import Err, Ok, Result
from voicecoach.application.token_hashing import hash_opaque_token, new_opaque_token
from voicecoach.application.use_cases.login_student import TokenPair
from voicecoach.domain.auth import RefreshToken

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime, timedelta
    from uuid import UUID

    from voicecoach.application.ports.access_tokens import AccessTokenIssuer
    from voicecoach.application.ports.auth_repositories import RefreshTokenRepository
    from voicecoach.application.ports.repositories import UnitOfWork


@dataclass(frozen=True, slots=True)
class RefreshTokens:
    refresh_token: str


@dataclass(frozen=True, slots=True)
class RefreshRejected:
    """Token inexistente, expirado, ou reuso detectado — uma resposta só."""


class RefreshTokensHandler:
    def __init__(
        self,
        *,
        refresh_tokens: RefreshTokenRepository,
        token_issuer: AccessTokenIssuer,
        unit_of_work: UnitOfWork,
        clock: Callable[[], datetime],
        new_id: Callable[[], UUID],
        access_token_ttl: timedelta,
        refresh_token_ttl: timedelta,
    ) -> None:
        self._refresh_tokens = refresh_tokens
        self._token_issuer = token_issuer
        self._uow = unit_of_work
        self._clock = clock
        self._new_id = new_id
        self._access_token_ttl = access_token_ttl
        self._refresh_token_ttl = refresh_token_ttl

    async def handle(
        self, command: RefreshTokens
    ) -> Result[TokenPair, RefreshRejected]:
        token_hash = hash_opaque_token(command.refresh_token)
        existente = await self._refresh_tokens.get_by_hash(token_hash)
        agora = self._clock()

        if existente is None:
            return Err(RefreshRejected())

        if existente.revoked_at is not None:
            # Reuso: este elo já foi rotacionado antes. A família inteira é
            # suspeita a partir daqui — ver o docstring do módulo.
            await self._refresh_tokens.revoke_family(existente.family_id, agora)
            await self._uow.commit()
            return Err(RefreshRejected())

        if not existente.is_usable(agora):
            return Err(RefreshRejected())

        await self._refresh_tokens.mark_revoked(existente.id, agora)
        refresh_claro, refresh_hash = new_opaque_token()
        novo = RefreshToken(
            id=self._new_id(),
            student_id=existente.student_id,
            family_id=existente.family_id,
            token_hash=refresh_hash,
            created_at=agora,
            expires_at=agora + self._refresh_token_ttl,
        )
        await self._refresh_tokens.add(novo)
        await self._uow.commit()

        access = self._token_issuer.issue(existente.student_id)
        return Ok(
            TokenPair(
                access_token=access,
                refresh_token=refresh_claro,
                expires_in_seconds=int(self._access_token_ttl.total_seconds()),
            )
        )
