"""social_identities: o vínculo de login social (CARD-060, ADR-0070)

Delta do CARD-060. Tabela nova, sem tocar nas existentes: `Credential`
continua sendo "prova por senha" e `SocialIdentity` é "prova por terceiro
verificado" — a mesma pessoa pode ter as duas, e o vínculo entre elas é
feito em `login_with_social.py`, não neste esquema.

`ON DELETE CASCADE` para `students.id`: ao contrário de `usage_events`
(ADR-0069), aqui não há nada a anonimizar — apagar a conta apaga o vínculo
social junto, sem ressalva.

`(provider, external_id)` único é a chave de identidade da pessoa PARA
aquele provedor (ver o docstring de `domain.auth.SocialIdentity`); `email`
não é único aqui de propósito — várias linhas (Google e Apple) podem trazer
o mesmo e-mail para o MESMO aluno, e isso é o caso feliz do card, não um
erro.

O tipo `social_provider` é enum nativo do Postgres, escrito à mão (não
`autogenerate`) pela mesma razão dos quatro enums anteriores deste projeto:
`values_callable` precisa gravar o *valor* do membro ("google"), não o
*nome* ("GOOGLE").

Revision ID: a4d8f2c19e6b
Revises: f3a1c9e4b7d2
Create Date: 2026-09-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a4d8f2c19e6b"
down_revision: str | Sequence[str] | None = "f3a1c9e4b7d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Cria a tabela, e com ela o tipo enum.

    **Quem cria o tipo é o `create_table`** — a mesma lição do CARD-013
    (`a3f1c8b52e94`): chamar `.create()` aqui antes teria o Postgres
    recusando com `DuplicateObjectError`, porque o `sa.Enum` da coluna
    também tenta criá-lo. Na descida não há simetria — é preciso remover o
    tipo à mão, ou ele fica órfão e a próxima subida falha com o mesmo erro.
    """
    provider = sa.Enum("google", "apple", name="social_provider")

    op.create_table(
        "social_identities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("provider", provider, nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "external_id", name="uq_social_identities_provider_external_id"
        ),
    )
    op.create_index(
        "ix_social_identities_student_id", "social_identities", ["student_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_social_identities_student_id", table_name="social_identities")
    op.drop_table("social_identities")
    sa.Enum(name="social_provider").drop(op.get_bind(), checkfirst=True)
