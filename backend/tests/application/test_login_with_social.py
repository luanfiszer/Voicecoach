"""``LoginWithSocialHandler`` — a regra de vínculo (CARD-060, ADR-0070).

A verificação criptográfica do token é testada nos adapters
(`test_google_identity_provider.py`, `test_apple_identity_provider.py`);
aqui o `SocialIdentityProvider` é um fake que já devolve o resultado —
o que este arquivo prova é a regra de "criar, linkar, ou reconhecer",
que é independente de qual provedor verificou o token.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fakes_pipeline import (
    FakeAccessTokenIssuer,
    FakeCredentialRepository,
    FakeRefreshTokenRepository,
    FakeSocialIdentityProvider,
    FakeSocialIdentityRepository,
    FakeStudentRepository,
    FakeUnitOfWork,
    RelogioFalso,
)
from voicecoach.application.ports.social_identity import (
    InvalidSocialTokenError,
    VerifiedSocialIdentity,
)
from voicecoach.application.result import Err, Ok
from voicecoach.application.use_cases.login_with_social import (
    InvalidSocialToken,
    LoginWithSocial,
    LoginWithSocialHandler,
)
from voicecoach.domain.auth import Credential, SocialIdentity, SocialProvider
from voicecoach.domain.student import Student

INICIO = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)


def montar(
    *,
    identidade_verificada: VerifiedSocialIdentity | None = None,
    erro: Exception | None = None,
    students: FakeStudentRepository | None = None,
    credentials: FakeCredentialRepository | None = None,
    social_identities: FakeSocialIdentityRepository | None = None,
) -> tuple[
    LoginWithSocialHandler,
    FakeStudentRepository,
    FakeCredentialRepository,
    FakeSocialIdentityRepository,
    FakeRefreshTokenRepository,
    FakeUnitOfWork,
]:
    students = students or FakeStudentRepository()
    credentials = credentials or FakeCredentialRepository()
    social_identities = social_identities or FakeSocialIdentityRepository()
    refresh_tokens = FakeRefreshTokenRepository()
    uow = FakeUnitOfWork()
    handler = LoginWithSocialHandler(
        identity_provider=FakeSocialIdentityProvider(identidade_verificada, erro=erro),
        social_identities=social_identities,
        credentials=credentials,
        students=students,
        refresh_tokens=refresh_tokens,
        token_issuer=FakeAccessTokenIssuer(),
        unit_of_work=uow,
        clock=RelogioFalso(inicio=INICIO),
        new_id=lambda: uuid4(),
        access_token_ttl=timedelta(minutes=15),
        refresh_token_ttl=timedelta(days=30),
    )
    return handler, students, credentials, social_identities, refresh_tokens, uow


def identidade_do_google(
    *,
    email: str = "aluno@example.com",
    sub: str = "google-sub-1",
    verificado: bool = True,
) -> VerifiedSocialIdentity:
    return VerifiedSocialIdentity(
        provider=SocialProvider.GOOGLE,
        external_id=sub,
        email=email,
        email_verified=verificado,
        display_name="Aluno do Google",
    )


async def test_primeira_vez_cria_student_credential_e_social_identity() -> None:
    handler, students, credentials, social_identities, refresh_tokens, uow = montar(
        identidade_verificada=identidade_do_google()
    )

    resultado = await handler.handle(
        LoginWithSocial(provider=SocialProvider.GOOGLE, token="id-token-qualquer")
    )

    assert isinstance(resultado, Ok)
    assert len(students.students) == 1
    aluno = next(iter(students.students.values()))
    assert aluno.display_name == "Aluno do Google"
    assert len(credentials.by_id) == 1
    credencial = next(iter(credentials.by_id.values()))
    assert credencial.email == "aluno@example.com"
    assert credencial.is_email_verified
    assert len(social_identities.by_id) == 1
    identidade = next(iter(social_identities.by_id.values()))
    assert identidade.student_id == aluno.id
    assert identidade.provider == SocialProvider.GOOGLE
    assert len(refresh_tokens.by_id) == 1
    assert uow.commits == 1


async def test_segunda_vez_reconhece_pelo_provider_e_external_id_sem_duplicar() -> None:
    aluno = Student(id=uuid4(), display_name="Aluno", created_at=INICIO)
    identidade_existente = SocialIdentity(
        id=uuid4(),
        student_id=aluno.id,
        provider=SocialProvider.GOOGLE,
        external_id="google-sub-1",
        email="aluno@example.com",
        created_at=INICIO,
    )
    handler, students, _credentials, social_identities, _refresh_tokens, uow = montar(
        identidade_verificada=identidade_do_google(),
        students=FakeStudentRepository(aluno),
        social_identities=FakeSocialIdentityRepository(identidade_existente),
    )

    resultado = await handler.handle(
        LoginWithSocial(provider=SocialProvider.GOOGLE, token="id-token-qualquer")
    )

    assert isinstance(resultado, Ok)
    assert len(students.students) == 1  # nenhum Student novo
    assert len(social_identities.by_id) == 1  # nenhuma SocialIdentity nova
    assert uow.commits == 1


async def test_email_ja_cadastrado_por_senha_linka_em_vez_de_duplicar() -> None:
    """O critério de aceite do card: a mesma pessoa, um cadastro só."""
    aluno = Student(id=uuid4(), display_name="Aluno de senha", created_at=INICIO)
    credencial = Credential(
        id=uuid4(),
        student_id=aluno.id,
        email="aluno@example.com",
        password_hash="hash-de-uma-senha-real",
        created_at=INICIO,
        email_verified_at=INICIO,
    )
    handler, students, credentials, social_identities, _refresh_tokens, uow = montar(
        identidade_verificada=identidade_do_google(),
        students=FakeStudentRepository(aluno),
        credentials=FakeCredentialRepository(credencial),
    )

    resultado = await handler.handle(
        LoginWithSocial(provider=SocialProvider.GOOGLE, token="id-token-qualquer")
    )

    assert isinstance(resultado, Ok)
    assert len(students.students) == 1  # nenhum Student novo — linkou
    assert len(credentials.by_id) == 1  # a credencial de senha não foi tocada
    assert credentials.by_id[credencial.id].password_hash == "hash-de-uma-senha-real"
    identidade = next(iter(social_identities.by_id.values()))
    assert identidade.student_id == aluno.id
    assert uow.commits == 1


async def test_provedor_confirma_email_que_ainda_nao_tinha_sido_verificado() -> None:
    """O Google/Apple já verificou — não faz sentido pedir confirmação de novo."""
    aluno = Student(id=uuid4(), display_name="Aluno", created_at=INICIO)
    credencial = Credential(
        id=uuid4(),
        student_id=aluno.id,
        email="aluno@example.com",
        password_hash="hash",
        created_at=INICIO,
        email_verified_at=None,  # ainda não confirmou o cadastro por senha
    )
    handler, _students, credentials, _social_identities, _refresh_tokens, _uow = montar(
        identidade_verificada=identidade_do_google(verificado=True),
        students=FakeStudentRepository(aluno),
        credentials=FakeCredentialRepository(credencial),
    )

    await handler.handle(
        LoginWithSocial(provider=SocialProvider.GOOGLE, token="id-token-qualquer")
    )

    assert credentials.by_id[credencial.id].is_email_verified


async def test_token_invalido_e_err_e_nada_e_criado() -> None:
    handler, students, credentials, social_identities, refresh_tokens, uow = montar(
        erro=InvalidSocialTokenError("assinatura não confere")
    )

    resultado = await handler.handle(
        LoginWithSocial(provider=SocialProvider.GOOGLE, token="token-adulterado")
    )

    assert isinstance(resultado, Err)
    assert isinstance(resultado.error, InvalidSocialToken)
    assert students.students == {}
    assert credentials.by_id == {}
    assert social_identities.by_id == {}
    assert refresh_tokens.by_id == {}
    assert uow.commits == 0


async def test_apple_usa_o_display_name_hint_so_na_primeira_vez() -> None:
    """A Apple nunca carrega nome no token — o cliente manda separado, e só
    importa quando a conta ainda não existe (ver o docstring do card).
    """
    identidade_da_apple = VerifiedSocialIdentity(
        provider=SocialProvider.APPLE,
        external_id="apple-sub-1",
        email="aluno@example.com",
        email_verified=True,
        display_name=None,  # a Apple nunca manda isto no token
    )
    handler, students, _credentials, _social_identities, _refresh_tokens, _uow = montar(
        identidade_verificada=identidade_da_apple
    )

    await handler.handle(
        LoginWithSocial(
            provider=SocialProvider.APPLE,
            token="identity-token-qualquer",
            display_name_hint="Nome Capturado No Primeiro Login",
        )
    )

    aluno = next(iter(students.students.values()))
    assert aluno.display_name == "Nome Capturado No Primeiro Login"


async def test_sem_nome_nenhum_usa_o_padrao() -> None:
    identidade_sem_nome = VerifiedSocialIdentity(
        provider=SocialProvider.APPLE,
        external_id="apple-sub-2",
        email="outro@example.com",
        email_verified=True,
        display_name=None,
    )
    handler, students, _credentials, _social_identities, _refresh_tokens, _uow = montar(
        identidade_verificada=identidade_sem_nome
    )

    await handler.handle(
        LoginWithSocial(provider=SocialProvider.APPLE, token="identity-token-qualquer")
    )

    aluno = next(iter(students.students.values()))
    assert aluno.display_name == "Aluno"
