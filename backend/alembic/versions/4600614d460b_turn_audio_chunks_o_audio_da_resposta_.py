"""turn_audio_chunks: o áudio da resposta vira sequência de trechos

Delta do ADR-0023 sobre o esquema do CARD-005. **A tabela ``turns`` não muda**:
``reply_audio_ref`` já tem o nome certo e passa a significar "o áudio inteiro
concatenado", que é exatamente o que ela sempre guardou. O delta é só a filha.

Escrita à mão, não por autogenerate: o esquema é pequeno e o `ondelete` da
foreign key é justamente o tipo de detalhe que o autogenerate não infere do
`cascade` do ORM (um é regra do Python, o outro é regra do Postgres — e só o
segundo protege de um `DELETE` feito fora da aplicação).

Nenhum backfill: não existe turn em banco. É o momento mais barato de pagar
esta mudança, e está escrito no ADR-0023 que foi por isso que ela veio agora.

Revision ID: 4600614d460b
Revises: d790e74af8f6
Create Date: 2026-08-19

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4600614d460b"
down_revision: str | Sequence[str] | None = "d790e74af8f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Cria a tabela dos trechos de áudio da resposta."""
    op.create_table(
        "turn_audio_chunks",
        sa.Column("turn_id", sa.Uuid(), nullable=False),
        # 0-based e denso. A chave primária composta abaixo é o que impede
        # índice repetido no banco — a mesma invariante que o domínio verifica
        # em `Turn.append_audio_chunk`, aqui contra escrita concorrente.
        sa.Column("index", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        # Duração de playback, em segundos fracionários (ADR-0023). Não é
        # dinheiro: `double precision` serve.
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        # A frase que gerou o trecho — é ela que o app mostra junto do áudio.
        sa.Column("text", sa.Text(), nullable=False),
        # Quando o aluno pôde ouvir este trecho. É a fonte da métrica de produto
        # do CARD-012 ("tempo até a primeira palavra"), não enfeite.
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["turn_id"], ["turns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("turn_id", "index"),
    )


def downgrade() -> None:
    """Desfaz a tabela filha. `turns` não foi tocada, então não há o que reverter lá."""
    op.drop_table("turn_audio_chunks")
