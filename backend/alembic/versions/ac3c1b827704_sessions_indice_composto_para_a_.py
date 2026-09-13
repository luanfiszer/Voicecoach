"""sessions: índice composto para a listagem do histórico

Delta do CARD-030, RNF2 ("índice antes da consulta"). A listagem filtra por
``student_id`` e ordena por ``started_at`` — **igualdade antes de faixa**, a
mesma ordem do índice de ``usage_events`` e pela mesma razão: o Postgres usa o
prefixo do índice para o ``=`` e o sufixo para a ordenação, o que dispensa o
sort.

O índice simples de ``student_id`` (criado no esquema inicial pelo
``index=True`` da coluna) **continua**: ele serve a foreign key e a qualquer
consulta que só filtre por aluno. Este é adicional, não substituto.

Revision ID: ac3c1b827704
Revises: 842710677a72
Create Date: 2026-09-13

"""

from collections.abc import Sequence

from alembic import op

revision: str = "ac3c1b827704"
down_revision: str | Sequence[str] | None = "842710677a72"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Cria o índice composto que sustenta `GET /v1/sessions`."""
    op.create_index(
        "ix_sessions_student_started", "sessions", ["student_id", "started_at"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_sessions_student_started", table_name="sessions")
