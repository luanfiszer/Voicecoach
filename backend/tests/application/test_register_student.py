"""``RegisterStudentHandler`` — o cadastro que não vaza (ADR-0007, CARD-049)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fakes_pipeline import (
    FakeCredentialRepository,
    FakeEmailSender,
    FakeEmailVerificationTokenRepository,
    FakePasswordHasher,
    FakeStudentRepository,
    FakeUnitOfWork,
    RelogioFalso,
)
from voicecoach.application.ports.repositories import ConflictingWriteError
from voicecoach.application.use_cases.register_student import (
    RegisterStudent,
    RegisterStudentHandler,
)
from voicecoach.domain.auth import Credential

INICIO = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)
NOVO_ID = UUID("11111111-1111-1111-1111-111111111111")


def montar(
    *, credencial_existente: Credential | None = None, email_falha: bool = False
) -> tuple[
    RegisterStudentHandler,
    FakeStudentRepository,
    FakeCredentialRepository,
    FakeEmailVerificationTokenRepository,
    FakeEmailSender,
    FakePasswordHasher,
    FakeUnitOfWork,
]:
    students = FakeStudentRepository()
    credentials = FakeCredentialRepository(
        *([credencial_existente] if credencial_existente else [])
    )
    verification_tokens = FakeEmailVerificationTokenRepository()
    sender = FakeEmailSender(falha=email_falha)
    hasher = FakePasswordHasher()
    uow = FakeUnitOfWork()
    ids = iter([NOVO_ID, uuid4(), uuid4()])
    handler = RegisterStudentHandler(
        students=students,
        credentials=credentials,
        verification_tokens=verification_tokens,
        hasher=hasher,
        email_sender=sender,
        unit_of_work=uow,
        clock=RelogioFalso(inicio=INICIO),
        new_id=lambda: next(ids),
        verification_ttl=timedelta(hours=24),
        verification_url=lambda token: f"https://api.example.com/confirm?token={token}",
    )
    return handler, students, credentials, verification_tokens, sender, hasher, uow


async def test_cadastro_novo_cria_student_e_credencial_e_envia_o_link() -> None:
    handler, students, credentials, tokens, sender, _hasher, uow = montar()

    await handler.handle(
        RegisterStudent(email="aluno@example.com", password="segredo123")
    )

    assert len(students.students) == 1
    assert len(credentials.by_id) == 1
    credencial = next(iter(credentials.by_id.values()))
    assert credencial.email == "aluno@example.com"
    assert credencial.password_hash == "hash-de-segredo123"
    assert credencial.email_verified_at is None
    assert len(tokens.by_id) == 1
    assert len(sender.enviados) == 1
    assert sender.enviados[0][0] == "aluno@example.com"
    assert "https://api.example.com/confirm?token=" in sender.enviados[0][1]
    assert uow.commits == 2


async def test_email_ja_cadastrado_nao_duplica_e_nao_reenvia() -> None:
    """RF do card: mesma resposta de um cadastro novo — aqui, verificável
    como "nada novo foi criado nem enviado"."""
    existente = Credential(
        id=uuid4(),
        student_id=uuid4(),
        email="aluno@example.com",
        password_hash="hash-antigo",
        created_at=INICIO,
    )
    handler, students, credentials, tokens, sender, _hasher, _uow = montar(
        credencial_existente=existente
    )

    await handler.handle(
        RegisterStudent(email="aluno@example.com", password="outra-senha")
    )

    assert len(students.students) == 0
    assert len(credentials.by_id) == 1
    assert credentials.by_id[existente.id].password_hash == "hash-antigo"
    assert len(tokens.by_id) == 0
    assert sender.enviados == []


async def test_senha_e_hasheada_mesmo_quando_o_email_ja_existe() -> None:
    """Timing: o custo de CPU do hash não pode distinguir os dois casos."""
    existente = Credential(
        id=uuid4(),
        student_id=uuid4(),
        email="aluno@example.com",
        password_hash="hash-antigo",
        created_at=INICIO,
    )
    handler, *_rest, hasher, _uow = montar(credencial_existente=existente)

    await handler.handle(
        RegisterStudent(email="aluno@example.com", password="qualquer")
    )

    assert hasher.chamadas_de_hash == 1


async def test_falha_no_envio_de_email_nao_impede_o_cadastro() -> None:
    """RNF do CARD-049: "o cadastro conclui e o e-mail é retentado"."""
    handler, students, credentials, tokens, sender, _hasher, uow = montar(
        email_falha=True
    )

    await handler.handle(
        RegisterStudent(email="aluno@example.com", password="segredo123")
    )

    assert len(students.students) == 1
    assert len(credentials.by_id) == 1
    assert len(tokens.by_id) == 1
    assert sender.enviados == []
    assert uow.commits == 2


class _UowComConflitoNoPrimeiroCommit:
    """Simula a corrida do docstring: outra requisição venceu entre o
    `get_by_email` e o `commit` desta."""

    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1
        message = "e-mail já cadastrado por outra requisição (simulado)"
        raise ConflictingWriteError(message)


async def test_corrida_entre_dois_registros_do_mesmo_email_nao_propaga() -> None:
    students = FakeStudentRepository()
    credentials = FakeCredentialRepository()
    tokens = FakeEmailVerificationTokenRepository()
    sender = FakeEmailSender()
    uow = _UowComConflitoNoPrimeiroCommit()
    ids = iter([NOVO_ID, uuid4()])
    handler = RegisterStudentHandler(
        students=students,
        credentials=credentials,
        verification_tokens=tokens,
        hasher=FakePasswordHasher(),
        email_sender=sender,
        unit_of_work=uow,
        clock=RelogioFalso(inicio=INICIO),
        new_id=lambda: next(ids),
        verification_ttl=timedelta(hours=24),
        verification_url=lambda token: f"https://api.example.com/confirm?token={token}",
    )

    await handler.handle(
        RegisterStudent(email="aluno@example.com", password="segredo123")
    )

    assert uow.commits == 1
    assert tokens.by_id == {}
    assert sender.enviados == []
