"""``POST /v1/auth/google``, ``POST /v1/auth/apple`` — login social (CARD-060,
ADR-0070).

**A regra de vínculo, por extenso.** Três casos, nesta ordem:

1. Já existe ``SocialIdentity`` para ``(provider, external_id)`` — é a mesma
   pessoa de uma vez anterior. Usa o ``student_id`` que já existe.
2. Não existe, mas já existe ``Credential`` com o mesmo e-mail (a pessoa se
   cadastrou por senha antes) — **linka**: a identidade social passa a
   apontar para o ``student_id`` daquela credencial, sem criar uma segunda
   conta. É o critério de aceite do card, e é a diferença entre "login
   social reduz atrito" e "login social duplica conta".
3. Não existe nenhum dos dois — é a primeira vez desta pessoa no produto.
   Cria ``Student`` + ``Credential`` (sem senha usável, ver ``_SEM_SENHA``)
   + ``SocialIdentity``, os três no mesmo instante.

**Por que não é preciso um segundo ``Result`` para "linkado" vs. "criado".**
Os dois casos emitem o MESMO par de tokens pelo MESMO caminho — não há
decisão diferente que o chamador (a rota) precise tomar sabendo qual dos
dois aconteceu. `Err` continua existindo só para o desfecho que É diferente
para o chamador: token inválido.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from voicecoach.application.ports.social_identity import InvalidSocialTokenError
from voicecoach.application.result import Err, Ok, Result
from voicecoach.application.token_hashing import new_opaque_token
from voicecoach.application.use_cases.login_student import TokenPair
from voicecoach.domain.auth import Credential, RefreshToken, SocialIdentity
from voicecoach.domain.student import Student

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime, timedelta
    from uuid import UUID

    from voicecoach.application.ports.access_tokens import AccessTokenIssuer
    from voicecoach.application.ports.auth_repositories import (
        CredentialRepository,
        RefreshTokenRepository,
        SocialIdentityRepository,
    )
    from voicecoach.application.ports.repositories import StudentRepository, UnitOfWork
    from voicecoach.application.ports.social_identity import (
        SocialIdentityProvider,
        VerifiedSocialIdentity,
    )
    from voicecoach.domain.auth import SocialProvider

_NOME_PADRAO = "Aluno"

# Um hash argon2id válido de uma senha que ninguém tem — mesmo idioma do
# `_HASH_DE_PREENCHIMENTO` de `login_student.py`, com um motivo diferente:
# lá o valor evita vazar "e-mail existe" por tempo de resposta; aqui ele
# existe porque uma conta puramente social **não tem senha própria**, e
# gravar uma coluna nulável que todo outro código (login, troca de senha)
# teria de checar seria mais caro que um valor que nunca confere. "Esqueci
# minha senha" continua funcionando sobre ele — é o caminho natural para um
# aluno social adicionar uma senha, não um caso especial.
_SEM_SENHA = (
    "$argon2id$v=19$m=65536,t=3,p=4$"
    "+SFm84HhngckKgo8b0PQ3Q$yMdD1BY+gbOj+s+8MKh+Cts2ZtsmwaHiaXdpnkhQ63s"
)


@dataclass(frozen=True, slots=True)
class LoginWithSocial:
    provider: SocialProvider
    token: str
    # Só a Apple manda isto, e só na primeira autorização — o `identityToken`
    # da Apple NUNCA carrega nome (ela entrega separado, fora do JWT, e só na
    # primeira vez). Ignorado quando a conta já existe.
    display_name_hint: str | None = None


@dataclass(frozen=True, slots=True)
class InvalidSocialToken:
    """Token adulterado, expirado, ou de audiência/emissor errado."""


class LoginWithSocialHandler:
    def __init__(
        self,
        *,
        identity_provider: SocialIdentityProvider,
        social_identities: SocialIdentityRepository,
        credentials: CredentialRepository,
        students: StudentRepository,
        refresh_tokens: RefreshTokenRepository,
        token_issuer: AccessTokenIssuer,
        unit_of_work: UnitOfWork,
        clock: Callable[[], datetime],
        new_id: Callable[[], UUID],
        access_token_ttl: timedelta,
        refresh_token_ttl: timedelta,
    ) -> None:
        self._identity_provider = identity_provider
        self._social_identities = social_identities
        self._credentials = credentials
        self._students = students
        self._refresh_tokens = refresh_tokens
        self._token_issuer = token_issuer
        self._uow = unit_of_work
        self._clock = clock
        self._new_id = new_id
        self._access_token_ttl = access_token_ttl
        self._refresh_token_ttl = refresh_token_ttl

    async def handle(
        self, command: LoginWithSocial
    ) -> Result[TokenPair, InvalidSocialToken]:
        try:
            verificado = await self._identity_provider.verify(command.token)
        except InvalidSocialTokenError:
            return Err(InvalidSocialToken())

        agora = self._clock()
        student_id = await self._vincular(command, verificado, agora)

        refresh_claro, refresh_hash = new_opaque_token()
        elo = RefreshToken(
            id=self._new_id(),
            student_id=student_id,
            family_id=self._new_id(),
            token_hash=refresh_hash,
            created_at=agora,
            expires_at=agora + self._refresh_token_ttl,
        )
        await self._refresh_tokens.add(elo)
        await self._uow.commit()

        access = self._token_issuer.issue(student_id)
        return Ok(
            TokenPair(
                access_token=access,
                refresh_token=refresh_claro,
                expires_in_seconds=int(self._access_token_ttl.total_seconds()),
            )
        )

    async def _vincular(
        self,
        command: LoginWithSocial,
        verificado: VerifiedSocialIdentity,
        agora: datetime,
    ) -> UUID:
        """Devolve o ``student_id`` certo, criando ou linkando quando falta.

        A ordem dos dois `await` que MODIFICAM estado (criar o `Student`
        antes da `Credential`) é a mesma do `RegisterStudentHandler`, e pela
        mesma razão: `credentials.student_id` referencia `students.id`.
        """
        identidade_existente = await self._social_identities.get_by_provider(
            verificado.provider, verificado.external_id
        )
        if identidade_existente is not None:
            return identidade_existente.student_id

        credencial_existente = await self._credentials.get_by_email(verificado.email)
        if credencial_existente is not None:
            student_id = credencial_existente.student_id
            if verificado.email_verified and not credencial_existente.is_email_verified:
                # O provedor já verificou este e-mail — confirmar de novo por
                # link seria pedir ao aluno para provar o que a Apple/Google
                # já provaram.
                await self._credentials.mark_email_verified(student_id, agora)
        else:
            student_id = self._new_id()
            nome = command.display_name_hint or verificado.display_name or _NOME_PADRAO
            await self._students.add(
                Student(id=student_id, display_name=nome, created_at=agora)
            )
            await self._credentials.add(
                Credential(
                    id=self._new_id(),
                    student_id=student_id,
                    email=verificado.email,
                    password_hash=_SEM_SENHA,
                    created_at=agora,
                    email_verified_at=agora if verificado.email_verified else None,
                )
            )

        await self._social_identities.add(
            SocialIdentity(
                id=self._new_id(),
                student_id=student_id,
                provider=verificado.provider,
                external_id=verificado.external_id,
                email=verificado.email,
                created_at=agora,
            )
        )
        return student_id
