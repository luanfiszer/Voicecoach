"""password_reset_tokens — "esqueci minha senha" (ADR-0007, CARD-049)

Mesma forma de `email_verification_tokens` (migration 77a5c9f67a67), tabela
própria: a posse do link autoriza coisas diferentes (ver o docstring de
`domain/auth.py::PasswordResetToken`).

Revision ID: 4a2903fb5821
Revises: 77a5c9f67a67
Create Date: 2026-09-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4a2903fb5821"
down_revision: str | Sequence[str] | None = "77a5c9f67a67"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_password_reset_tokens_student_id",
        "password_reset_tokens",
        ["student_id"],
    )


def downgrade() -> None:
    op.drop_table("password_reset_tokens")
