"""``POST /v1/auth/login`` — e-mail+senha vira um par de tokens (ADR-0007).

**Por que login não checa e-mail verificado.** O ADR-0007 é explícito: a
verificação bloqueia o primeiro *turn*, não o login — deixar entrar e barrar
no turn evita que uma falha de entregabilidade de e-mail vire uma tela morta
no primeiro minuto de uso. A checagem mora em
``api.dependencies.enforce_verified_email``.

**Por que ``InvalidCredentials`` é ``Result``, não exceção.** Senha errada é
o desfecho mais comum de um formulário de login digitado por um humano — é a
definição de "normal do negócio que não é bug" do ADR-0017/0039.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from voicecoach.application.result import Err, Ok, Result
from voicecoach.application.token_hashing import new_opaque_token
from voicecoach.domain.auth import RefreshToken

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime, timedelta
    from uuid import UUID

    from voicecoach.application.ports.access_tokens import AccessTokenIssuer
    from voicecoach.application.ports.auth_repositories import (
        CredentialRepository,
        RefreshTokenRepository,
    )
    from voicecoach.application.ports.password_hasher import PasswordHasher
    from voicecoach.application.ports.repositories import StudentRepository, UnitOfWork

# Um hash ``argon2id`` válido de uma senha que ninguém tem — gerado uma vez,
# offline (não é segredo: o valor não protege nada, só preenche o formato).
# **Por que um valor fixo em vez de recalcular a cada request.** `hasher.hash`
# custa os mesmos ~50ms que `verify` — recalcular dobraria o custo do caminho
# "e-mail não existe" em vez de igualá-lo ao caminho "e-mail existe, senha
# errada", que é a simetria que o critério de aceite pede. Gatilho para
# regenerar: nunca — ele não precisa corresponder a senha nenhuma real.
_HASH_DE_PREENCHIMENTO = (
    "$argon2id$v=19$m=65536,t=3,p=4$"
    "+SFm84HhngckKgo8b0PQ3Q$yMdD1BY+gbOj+s+8MKh+Cts2ZtsmwaHiaXdpnkhQ63s"
)


@dataclass(frozen=True, slots=True)
class LoginStudent:
    email: str
    password: str


@dataclass(frozen=True, slots=True)
class InvalidCredentials:
    """E-mail inexistente ou senha errada — a mesma resposta para os dois."""


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in_seconds: int


class LoginStudentHandler:
    def __init__(
        self,
        *,
        credentials: CredentialRepository,
        students: StudentRepository,
        refresh_tokens: RefreshTokenRepository,
        hasher: PasswordHasher,
        token_issuer: AccessTokenIssuer,
        unit_of_work: UnitOfWork,
        clock: Callable[[], datetime],
        new_id: Callable[[], UUID],
        access_token_ttl: timedelta,
        refresh_token_ttl: timedelta,
    ) -> None:
        self._credentials = credentials
        self._students = students
        self._refresh_tokens = refresh_tokens
        self._hasher = hasher
        self._token_issuer = token_issuer
        self._uow = unit_of_work
        self._clock = clock
        self._new_id = new_id
        self._access_token_ttl = access_token_ttl
        self._refresh_token_ttl = refresh_token_ttl

    async def handle(
        self, command: LoginStudent
    ) -> Result[TokenPair, InvalidCredentials]:
        credential = await self._credentials.get_by_email(command.email)
        hash_a_comparar = (
            credential.password_hash if credential else _HASH_DE_PREENCHIMENTO
        )
        senha_confere = await self._hasher.verify(command.password, hash_a_comparar)

        if credential is None or not senha_confere:
            return Err(InvalidCredentials())

        # A conta pode estar marcada para exclusão (CARD-051, ADR-0069) sem
        # que a credencial já tenha sido apagada — o expurgo é assíncrono. A
        # mesma resposta de senha errada, pela mesma razão do
        # `_HASH_DE_PREENCHIMENTO`: não vazar "esta conta existe, mas foi
        # excluída" para quem tenta logar.
        aluno = await self._students.get(credential.student_id)
        if aluno is None or not aluno.is_active:
            return Err(InvalidCredentials())

        agora = self._clock()
        refresh_claro, refresh_hash = new_opaque_token()
        token = RefreshToken(
            id=self._new_id(),
            student_id=credential.student_id,
            family_id=self._new_id(),
            token_hash=refresh_hash,
            created_at=agora,
            expires_at=agora + self._refresh_token_ttl,
        )
        await self._refresh_tokens.add(token)
        await self._uow.commit()

        access = self._token_issuer.issue(credential.student_id)
        return Ok(
            TokenPair(
                access_token=access,
                refresh_token=refresh_claro,
                expires_in_seconds=int(self._access_token_ttl.total_seconds()),
            )
        )
