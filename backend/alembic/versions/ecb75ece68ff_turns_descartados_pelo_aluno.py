"""turns descartados pelo aluno

Revision ID: ecb75ece68ff
Revises: 472d4f6cb79c
Create Date: 2026-09-13 08:45:55.975490

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ecb75ece68ff"
down_revision: str | Sequence[str] | None = "472d4f6cb79c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Nulável, sem backfill: toda linha existente nunca foi descartada (CARD-032)."""
    op.add_column(
        "turns", sa.Column("discarded_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("turns", "discarded_at")
