"""Portas de persistência (ADR-0004).

Declaradas como ``Protocol``: tipagem **estrutural**. Um adapter satisfaz a
porta por ter os métodos com a assinatura certa — não herda nada, não se
registra em lugar nenhum, e o ``domain``/``application`` nunca importa o
adapter. É a diferença para C#, onde a classe precisa declarar ``: IRepository``
para o compilador aceitar.

Consequência prática em teste: um fake é uma classe comum com os métodos
certos, sem framework de mock. E o erro de um fake que não satisfaz a porta
aparece no ``mypy``, **antes** de qualquer execução — não no meio do teste.

**Quem faz commit não é o repositório.** Estes métodos registram a intenção na
unidade de trabalho; confirmar a transação é decisão de quem a abriu (a borda,
por request — CARD-010). O contrário — cada repositório comitando o que fez —
tornaria impossível salvar Turn e Correction atomicamente no mesmo turno.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from uuid import UUID

    from voicecoach.domain.session import Session
    from voicecoach.domain.student import Student
    from voicecoach.domain.turn import Turn


class StudentRepository(Protocol):
    """Acesso às contas de aluno."""

    async def add(self, student: Student) -> None: ...

    async def get(self, student_id: UUID) -> Student | None: ...


class SessionRepository(Protocol):
    """Acesso às conversas."""

    async def add(self, session: Session) -> None: ...

    async def get(self, session_id: UUID) -> Session | None: ...

    async def update(self, session: Session) -> None: ...


class TurnRepository(Protocol):
    """Acesso aos turnos.

    ``update`` existe porque a entidade de domínio **não** é o objeto mapeado
    pelo SQLAlchemy (ADR-0004): mudar o `Turn` em memória não sensibiliza
    sessão nenhuma, então o pipeline do worker (CARD-009) precisa dizer
    explicitamente que quer gravar o novo estado. É o preço consciente do
    mapeamento entidade↔linha — e o contraste com o change tracking do EF Core.
    """

    async def add(self, turn: Turn) -> None: ...

    async def get(self, turn_id: UUID) -> Turn | None: ...

    async def update(self, turn: Turn) -> None: ...
