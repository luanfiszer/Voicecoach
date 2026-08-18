"""seed do student de desenvolvimento

Enquanto não há autenticação (Fase 3), a fatia vertical precisa de **um** aluno
para as sessões pertencerem a alguém. Ele nasce aqui, com id fixo, para que o
worker, os testes e o app de desenvolvimento falem do mesmo registro sem
combinar nada.

Duas escolhas conscientes:

- **Migration de dados, não script.** O critério de aceite do CARD-005 é
  "``alembic upgrade head`` num banco vazio e o Student dev existe" — um script
  à parte transformaria isso em passo manual que alguém esquece.
- **Idempotente** (``ON CONFLICT DO NOTHING``): rodar de novo não explode, e
  quem já tem o registro não perde o que mudou nele.

Dívida assumida: é dado de desenvolvimento numa migration que rodaria também em
produção. Aceitável enquanto não existe produção nem cadastro; a Fase 3 (auth
real) revisita — e o gatilho é o primeiro Student criado por cadastro de
verdade.

Revision ID: d790e74af8f6
Revises: 6dcdc3fe7dd3
Create Date: 2026-08-18

"""

from collections.abc import Sequence

from alembic import op

revision: str = "d790e74af8f6"
down_revision: str | Sequence[str] | None = "6dcdc3fe7dd3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Literal de propósito: migration é registro histórico e não deve importar
# código da aplicação, que muda com o tempo. A mesma constante, para uso do
# código, mora em `voicecoach.adapters.persistence.seed.DEV_STUDENT_ID` — e um
# teste garante que as duas não divirjam.
_DEV_STUDENT_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.execute(
        f"""
        INSERT INTO students (id, display_name, created_at)
        VALUES ('{_DEV_STUDENT_ID}', 'Aluno de desenvolvimento', NOW())
        ON CONFLICT (id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM students WHERE id = '{_DEV_STUDENT_ID}'")
