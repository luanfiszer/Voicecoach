"""turn_corrections: a correção deixa de passar e vira dado

Delta do CARD-013. **A tabela ``turns`` não muda**, e a ausência é a decisão: os
quatro campos texto do contrato ``/v1`` (``has_mistakes``, ``original``,
``corrected``, ``tip``) **não** ganham coluna. Eles continuam existindo na borda
HTTP, derivados desta tabela por ``legacy_summary`` — persisti-los seria gravar
a mesma verdade duas vezes, que é o que o ADR-0016 recusou ao derivar a etapa do
Turn em vez de gravá-la.

Escrita à mão, como a do CARD-018, e pelas mesmas duas razões: o ``ondelete`` da
foreign key não sai do ``cascade`` do ORM (um é regra do Python, o outro do
Postgres, e só o segundo protege de um ``DELETE`` fora da aplicação), e os dois
tipos enum precisam nascer com os **valores** dos membros, não com os nomes.

Nenhum backfill: não existe correção em banco, porque até agora ela só
transitava. É o momento mais barato de pagar esta mudança.

Revision ID: a3f1c8b52e94
Revises: b1c4e7a92f30
Create Date: 2026-08-26

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3f1c8b52e94"
down_revision: str | Sequence[str] | None = "b1c4e7a92f30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Os valores são os dos membros do `StrEnum`, em minúsculas — o mesmo que o
# `values_callable` do modelo produz. Divergir aqui daria um banco que aceita
# 'GRAMMAR' e uma aplicação que só escreve 'grammar', e o erro apareceria como
# `InvalidTextRepresentation` na primeira gravação real.
_TIPOS = ("grammar", "vocabulary", "preposition", "word_order", "other")
_SEVERIDADES = ("minor", "moderate", "major")


def upgrade() -> None:
    """Cria a tabela das correções, e com ela os dois tipos enum."""
    # **Quem cria os dois tipos é o `create_table`**, e a assimetria com o
    # `downgrade` (que os remove à mão) é a parte que custou uma execução para
    # descobrir: chamar `.create()` aqui ANTES do `create_table` faz o Postgres
    # recusar a tabela com `DuplicateObjectError: type "correction_type" already
    # exists`, porque o `sa.Enum` da coluna também tenta criá-lo. Na descida não
    # há simetria nenhuma — `drop_table` deixa os tipos órfãos, e um tipo órfão
    # faz a próxima subida falhar exatamente com aquele mesmo erro.
    tipo = sa.Enum(*_TIPOS, name="correction_type")
    severidade = sa.Enum(*_SEVERIDADES, name="correction_severity")

    op.create_table(
        "turn_corrections",
        sa.Column("turn_id", sa.Uuid(), nullable=False),
        # 0-based e denso, como o índice do trecho de áudio — e aqui ele carrega
        # um segundo significado: é a ORDEM PEDAGÓGICA em que o professor
        # priorizou as correções. É de `index = 0` que saem os campos velhos do
        # contrato `/v1`.
        sa.Column("index", sa.Integer(), nullable=False),
        sa.Column("type", tipo, nullable=False),
        # Os três campos livres são `Text` e não `String(n)`: nenhum tem limite
        # que o negócio saiba defender, e no Postgres os dois têm o mesmo custo.
        sa.Column("original_excerpt", sa.Text(), nullable=False),
        sa.Column("corrected_form", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("severity", severidade, nullable=False),
        sa.ForeignKeyConstraint(["turn_id"], ["turns.id"], ondelete="CASCADE"),
        # A mesma invariante que `Turn.attach_corrections` verifica no domínio,
        # aqui contra escrita concorrente que passou por ela em outro processo.
        sa.PrimaryKeyConstraint("turn_id", "index"),
    )


def downgrade() -> None:
    """Desfaz a tabela e os dois tipos enum, nesta ordem.

    A ordem é obrigatória: o Postgres recusa `DROP TYPE` enquanto uma coluna
    ainda o usa.
    """
    op.drop_table("turn_corrections")
    sa.Enum(name="correction_severity").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="correction_type").drop(op.get_bind(), checkfirst=True)
