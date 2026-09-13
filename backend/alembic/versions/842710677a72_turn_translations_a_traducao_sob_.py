"""turn_translations: a tradução sob demanda vira linha

Delta do CARD-036. A tabela guarda a tradução de um texto **que o produto já
produziu** (a resposta do professor ou a explicação de uma correção), com o
custo congelado na escrita — a mesma disciplina do ``usage_events``
(ADR-0051).

**Por que tabela e não coluna** (RNF1 do card): o texto traduzido de uma
correção não cabe em ``turn_corrections`` sem quebrar o write-once que o
ADR-0049 fixou para aquela entidade, e uma coluna em ``turns`` só resolveria
metade dos alvos. Uma tabela com a identidade natural
``(turn_id, target, index)`` cobre os dois e deixa o agregado do turn intacto.

Escrita à mão, pelas mesmas razões da migration das correções: o ``ondelete``
da foreign key não sai do ``cascade`` do ORM, e o tipo enum precisa nascer com
os **valores** dos membros, não com os nomes.

Nenhum backfill: não existe tradução em banco — o endpoint nasce com esta
migration.

Revision ID: 842710677a72
Revises: ecb75ece68ff
Create Date: 2026-09-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "842710677a72"
down_revision: str | Sequence[str] | None = "ecb75ece68ff"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Os valores dos membros do `StrEnum`, em minúsculas — o mesmo que o
# `values_callable` do modelo produz. Divergir aqui daria um banco que aceita
# 'REPLY' e uma aplicação que só escreve 'reply'.
_ALVOS = ("reply", "correction")


def upgrade() -> None:
    """Cria a tabela das traduções, e com ela o tipo enum do alvo."""
    # Quem cria o tipo é o `create_table` — chamar `.create()` antes faz o
    # Postgres recusar com `DuplicateObjectError`, porque o `sa.Enum` da coluna
    # também tenta criá-lo. Ver a nota completa na migration das correções.
    alvo = sa.Enum(*_ALVOS, name="translation_target")

    op.create_table(
        "turn_translations",
        sa.Column("turn_id", sa.Uuid(), nullable=False),
        sa.Column("target", alvo, nullable=False),
        # Sempre 0 para `reply` (há uma resposta por turn); o índice da correção
        # para `correction`. Inteiro sempre presente em vez de nulável porque
        # NULL não participa de chave primária no Postgres.
        sa.Column("index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        # O modelo que RESPONDEU (id datado), não o alias da configuração.
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        # `NUMERIC` e nunca `DOUBLE PRECISION` (ADR-0013), com a mesma precisão
        # e escala do `usage_events`. Nulável com o mesmo significado: "não
        # sabemos precificar este modelo", nunca "grátis".
        sa.Column(
            "estimated_cost_usd", sa.Numeric(precision=12, scale=8), nullable=True
        ),
        sa.ForeignKeyConstraint(["turn_id"], ["turns.id"], ondelete="CASCADE"),
        # É esta chave que implementa o RF4 do lado do banco: duas requisições
        # simultâneas para o mesmo texto passam as duas pela consulta e só uma
        # grava.
        sa.PrimaryKeyConstraint("turn_id", "target", "index"),
    )


def downgrade() -> None:
    """Desfaz a tabela e o tipo enum, nesta ordem.

    A ordem é obrigatória: o Postgres recusa `DROP TYPE` enquanto uma coluna
    ainda o usa, e `drop_table` sozinho deixaria o tipo órfão — o que faria a
    próxima subida falhar com `DuplicateObjectError`.
    """
    op.drop_table("turn_translations")
    sa.Enum(name="translation_target").drop(op.get_bind())
