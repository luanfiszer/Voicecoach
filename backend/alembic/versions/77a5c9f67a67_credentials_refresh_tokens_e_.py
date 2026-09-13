"""credentials, refresh_tokens, email_verification_tokens — a auth do ADR-0007

Delta do CARD-049. Três tabelas novas, nenhuma mudança em `students`: e-mail e
senha vivem em `credentials`, separada de propósito (ver o docstring de
`domain/auth.py`) — o CARD-060 (login social) vai apontar para o mesmo
`student_id` sem tocar nesta tabela.

Escrita à mão, como as anteriores desta série, pela mesma razão de sempre: o
`ondelete` da foreign key não sai do `cascade` do ORM (só o primeiro protege
de um `DELETE` fora da aplicação).

Nenhum backfill: não existe conta com senha em produção até este card existir.

Revision ID: 77a5c9f67a67
Revises: ac3c1b827704
Create Date: 2026-09-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "77a5c9f67a67"
down_revision: str | Sequence[str] | None = "ac3c1b827704"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "credentials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id"),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_refresh_tokens_student_id", "refresh_tokens", ["student_id"])
    # A detecção de reuso filtra por família em massa (`revoke_family`) — sem
    # este índice, cada reuso detectado seria um `seq scan` na tabela inteira.
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])

    op.create_table(
        "email_verification_tokens",
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
        "ix_email_verification_tokens_student_id",
        "email_verification_tokens",
        ["student_id"],
    )


def downgrade() -> None:
    op.drop_table("email_verification_tokens")
    op.drop_table("refresh_tokens")
    op.drop_table("credentials")
