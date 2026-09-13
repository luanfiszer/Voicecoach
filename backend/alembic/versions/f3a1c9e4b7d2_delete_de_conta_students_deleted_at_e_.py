"""delete de conta: students.deleted_at e usage_events sobrevive anônimo

Delta do CARD-051 (ADR-0069). Duas mudanças, uma tabela nova de coluna e um
ajuste estrutural em `usage_events`:

1. `students.deleted_at` — a exclusão lógica e imediata. Nulável, sem
   default: toda conta existente já nasce ativa.
2. `usage_events.turn_id` **perde a restrição de chave estrangeira** com
   `turns.id`. É a única forma de apagar um `Turn` (o que o expurgo de conta
   precisa fazer) sem apagar o `UsageEvent` que ele gerou — `turn_id` é a
   chave primária da tabela, então `SET NULL` é impossível, e manter
   `CASCADE`/`RESTRICT` obrigaria a escolher entre apagar o custo ou nunca
   poder apagar o turn. A coluna continua existindo, com o mesmo valor de
   sempre — só deixa de ser *enforced* contra `turns`.
3. `usage_events.student_id` passa a aceitar `NULL`, e seu `ON DELETE CASCADE`
   vira `ON DELETE SET NULL`. É o que anonimiza a linha no MESMO instante em
   que o `Student` é apagado — o banco faz isso sozinho, sem um `UPDATE`
   explícito no job de expurgo que alguém poderia esquecer de repetir num
   caminho de exclusão futuro.

Nenhum backfill: nenhum `Student` tinha `deleted_at` e nenhum `usage_events`
tinha `student_id` nulo antes desta migration — os dois só passam a existir a
partir do primeiro delete de conta.

Revision ID: f3a1c9e4b7d2
Revises: 4a2903fb5821
Create Date: 2026-09-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f3a1c9e4b7d2"
down_revision: str | Sequence[str] | None = "4a2903fb5821"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "students",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Nomes reais no banco (criados sem `name=` explícito na migration
    # original, CARD-014) — confirmados via `\d usage_events` antes de
    # escrever esta migration, não adivinhados.
    op.drop_constraint("usage_events_turn_id_fkey", "usage_events", type_="foreignkey")
    op.drop_constraint(
        "usage_events_student_id_fkey", "usage_events", type_="foreignkey"
    )
    op.alter_column("usage_events", "student_id", nullable=True)
    op.create_foreign_key(
        "usage_events_student_id_fkey",
        "usage_events",
        "students",
        ["student_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # `turn_id` fica sem FK nenhuma — não recriamos a constraint.


def downgrade() -> None:
    """Desfaz na ordem inversa.

    **`op.alter_column(..., nullable=False)` falha se alguma linha já tiver
    `student_id NULL`** (produzida por um delete de conta real depois do
    upgrade) — downgrade de dado anonimizado não é o caminho que este ADR
    previu, e o erro é o comportamento certo, não um bug da migration.
    """
    op.drop_constraint(
        "usage_events_student_id_fkey", "usage_events", type_="foreignkey"
    )
    op.alter_column("usage_events", "student_id", nullable=False)
    op.create_foreign_key(
        "usage_events_student_id_fkey",
        "usage_events",
        "students",
        ["student_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "usage_events_turn_id_fkey",
        "usage_events",
        "turns",
        ["turn_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_column("students", "deleted_at")
