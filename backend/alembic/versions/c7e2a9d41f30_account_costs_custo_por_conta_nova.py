"""account_costs: o custo por conta nova, consultável sem dashboard (CARD-054)

Uma VIEW, não uma tabela: o número é derivado de `usage_events` (turns) e
`turn_translations` (traduções), que já são a fonte da verdade do que foi
consumido (ADR-0051). Persistir o agregado seria dado duplicado que sai de
sincronia (ADR-0016). Consulta típica, de `psql`:

    SELECT date_trunc('week', created_at) AS semana, count(*) AS contas,
           avg(cost_first_7_days_usd) AS custo_medio_7d
      FROM account_costs GROUP BY 1 ORDER BY 1;

`has_unpriced_events` existe pela mesma regra do `estimated_cost_usd`
nulo: evento de modelo fora da tabela de preço não pode virar zero e fazer a
conta parecer grátis — ele marca a linha como "custo incompleto".

Conta excluída (ADR-0069): os `usage_events` dela ficam com `student_id`
nulo e as traduções somem em cascata, então ela sai da view com custo zero
depois do purge. É o preço aceito da anonimização; o custo continua no
total global de `usage_events`.

Revision ID: c7e2a9d41f30
Revises: a4d8f2c19e6b
Create Date: 2026-10-01

"""

from collections.abc import Sequence

from alembic import op

revision: str = "c7e2a9d41f30"
down_revision: str | None = "a4d8f2c19e6b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE VIEW account_costs AS
        SELECT
            s.id AS student_id,
            s.created_at,
            s.deleted_at IS NOT NULL AS deleted,
            COALESCE(u.turns_30d, 0) AS turns_first_30_days,
            COALESCE(u.cost_7d, 0) + COALESCE(t.cost_7d, 0)
                AS cost_first_7_days_usd,
            COALESCE(u.cost_30d, 0) + COALESCE(t.cost_30d, 0)
                AS cost_first_30_days_usd,
            COALESCE(u.unpriced, 0) + COALESCE(t.unpriced, 0) > 0
                AS has_unpriced_events
        FROM students s
        LEFT JOIN LATERAL (
            SELECT
                count(*) FILTER (
                    WHERE e.occurred_at < s.created_at + interval '30 days'
                ) AS turns_30d,
                sum(e.estimated_cost_usd) FILTER (
                    WHERE e.occurred_at < s.created_at + interval '7 days'
                ) AS cost_7d,
                sum(e.estimated_cost_usd) FILTER (
                    WHERE e.occurred_at < s.created_at + interval '30 days'
                ) AS cost_30d,
                count(*) FILTER (WHERE e.estimated_cost_usd IS NULL) AS unpriced
            FROM usage_events e
            WHERE e.student_id = s.id
        ) u ON true
        LEFT JOIN LATERAL (
            SELECT
                sum(tt.estimated_cost_usd) FILTER (
                    WHERE tt.created_at < s.created_at + interval '7 days'
                ) AS cost_7d,
                sum(tt.estimated_cost_usd) FILTER (
                    WHERE tt.created_at < s.created_at + interval '30 days'
                ) AS cost_30d,
                count(*) FILTER (WHERE tt.estimated_cost_usd IS NULL) AS unpriced
            FROM turn_translations tt
            JOIN turns tu ON tu.id = tt.turn_id
            JOIN sessions se ON se.id = tu.session_id
            WHERE se.student_id = s.id
        ) t ON true
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW account_costs")
