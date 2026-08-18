"""esquema inicial: students, sessions, turns

Gerada por autogenerate no CARD-005 e ajustada à mão em um ponto: o
``downgrade`` também derruba o tipo ``turn_status``. ``drop_table`` remove a
tabela, mas o ``TYPE`` criado para a enum **sobrevive** no Postgres — e o
``upgrade`` seguinte falharia com "type turn_status already exists". É a
pegadinha clássica de enum nativo com Alembic, e só aparece em quem roda
downgrade.

Revision ID: 6dcdc3fe7dd3
Revises:
Create Date: 2026-08-18

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6dcdc3fe7dd3"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_turn_status = sa.Enum(
    "queued", "processing", "completed", "failed", name="turn_status"
)


def upgrade() -> None:
    """Cria o esquema do domínio mínimo."""
    op.create_table(
        "students",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        # Nulo = sessão em andamento (estado derivado, não gravado).
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_sessions_student_id"), "sessions", ["student_id"], unique=False
    )
    op.create_table(
        "turns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("input_audio_ref", sa.String(length=512), nullable=False),
        # INTERVAL: insumo da quota em minutos falados (CARD-015).
        sa.Column("audio_duration", sa.Interval(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", _turn_status, nullable=False),
        # Artefatos do pipeline: nulo = "ainda não aconteceu". É o que permite
        # derivar a etapa exibida ao app em vez de gravá-la (ADR-0016).
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("transcribed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reply_text", sa.Text(), nullable=True),
        sa.Column("replied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reply_audio_ref", sa.String(length=512), nullable=True),
        sa.Column("synthesized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_processing_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_turns_session_id"), "turns", ["session_id"], unique=False)
    op.create_index(op.f("ix_turns_status"), "turns", ["status"], unique=False)


def downgrade() -> None:
    """Desfaz o esquema — inclusive o tipo enum, que o autogenerate esquece."""
    op.drop_index(op.f("ix_turns_status"), table_name="turns")
    op.drop_index(op.f("ix_turns_session_id"), table_name="turns")
    op.drop_table("turns")
    op.drop_index(op.f("ix_sessions_student_id"), table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("students")
    _turn_status.drop(op.get_bind(), checkfirst=True)
