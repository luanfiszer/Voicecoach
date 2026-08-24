"""turns.idempotency_key: a chave do POST vira coluna, com índice único parcial

Delta do CARD-010. O card original supunha Redis (`SETNX` + TTL) e nomeava o
risco sem resolvê-lo: a janela entre "criei o Turn" e "enfileirei". Com a chave
no Postgres a janela some, porque a chave e o Turn nascem no **mesmo commit** —
ou os dois existem, ou nenhum existe. Não há estado em que a chave aponte para
nada.

**O índice é PARCIAL** (`WHERE idempotency_key IS NOT NULL`) e essa é a única
sutileza aqui. Um índice único comum sobre uma coluna nula funcionaria no
Postgres (nulos não colidem entre si no padrão SQL), mas o parcial diz a
intenção em vez de depender dessa regra, e não indexa as linhas que o worker e
os testes criam sem passar pela borda HTTP.

Escrita à mão, não por autogenerate: `postgresql_where` é justamente o tipo de
detalhe de dialeto que se confere lendo, não confiando.

Nenhum backfill: os Turns existentes (se houver) ficam com a chave nula, que é
o que "nasceu antes da idempotência" significa.

Revision ID: b1c4e7a92f30
Revises: 4600614d460b
Create Date: 2026-08-23

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b1c4e7a92f30"
down_revision: str | Sequence[str] | None = "4600614d460b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "turns",
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_turns_idempotency_key",
        "turns",
        ["idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_turns_idempotency_key", table_name="turns")
    op.drop_column("turns", "idempotency_key")
