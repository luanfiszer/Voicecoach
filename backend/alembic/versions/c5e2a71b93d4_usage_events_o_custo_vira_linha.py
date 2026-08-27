"""usage_events: o custo deixa de ser estimativa e vira linha

Delta do CARD-014 (ADR-0051). O ``TokenUsage`` real atravessava a porta do
professor desde o CARD-007 e era **descartado** pelo caso de uso; toda projeção
de margem do projeto vinha de uma estimativa de 2026-08-19.

**A tabela ``turns`` não muda, e nenhum ``relationship`` novo nasce nela.** É a
diferença deliberada em relação à migration do CARD-013: ``turn_corrections`` é
coleção filha do agregado, carregada em toda leitura de turn; ``usage_events`` é
lida em **agregação** e ficaria pesando no caminho crítico de 1,8 s sem
responder a nenhuma pergunta daquela leitura.

Escrita à mão, e não por ``autogenerate``, pelas mesmas razões dos deltas
anteriores: o ``ondelete`` das foreign keys não sai do ``cascade`` do ORM (um é
regra do Python, o outro do Postgres, e só o segundo protege de um ``DELETE``
disparado fora da aplicação).

**Nenhum tipo enum aqui**, ao contrário do CARD-013 — e a ausência é decisão, não
esquecimento: ``llm_model``, ``stt_provider`` e ``tts_provider`` são ``VARCHAR``
porque o conjunto **não é fechado**. O modelo é configuração (ADR-0009), e um
tipo enum do Postgres exigiria uma migration a cada modelo novo do provedor. Sem
enum, também não existe a armadilha de ordem que custou uma execução naquele
card (``DuplicateObjectError`` por chamar ``.create()`` antes do ``create_table``).

**Nenhum backfill.** Não existe custo em banco: até agora ele era jogado fora. É
o momento mais barato de pagar esta mudança — e a consequência honesta é que
todo turn processado antes desta migration é custo perdido para sempre.

Revision ID: c5e2a71b93d4
Revises: a3f1c8b52e94
Create Date: 2026-08-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c5e2a71b93d4"
down_revision: str | Sequence[str] | None = "a3f1c8b52e94"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Cria a tabela de custo e o índice que a agregação do CARD-015 vai usar."""
    op.create_table(
        "usage_events",
        # **PK, e não coluna comum com id surrogate ao lado.** Um turn tem um
        # custo, e é a chave primária que impõe isso: uma segunda escrita vira
        # `IntegrityError` em vez de duplicar silenciosamente toda soma de custo
        # daquele aluno.
        sa.Column("turn_id", sa.Uuid(), nullable=False),
        # Desnormalizado de propósito: já é derivável por
        # `turns → sessions → student_id`. Está aqui porque a consulta que o
        # CARD-015 vai rodar DENTRO do POST é `GROUP BY student_id`, e dois joins
        # no caminho crítico de um request para buscar uma coluna que cabe na
        # linha é economia de espaço paga em latência.
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        # O modelo que RESPONDEU (`message.model`), não o alias pedido em
        # `TEACHER_MODEL`: é o id datado que tem preço na tabela.
        sa.Column("llm_model", sa.String(length=120), nullable=False),
        sa.Column("llm_input_tokens", sa.Integer(), nullable=False),
        # As duas contagens de cache, separadas (ADR-0021, item 3). Hoje 0 em
        # toda linha, e é exatamente para isso que existem: o dia em que uma
        # delas deixar de ser zero é o gatilho de reabrir o prompt caching.
        # `NOT NULL` de propósito — zero é dado; nulo aqui seria "não medimos",
        # que nunca é verdade.
        sa.Column("llm_cache_creation_tokens", sa.Integer(), nullable=False),
        sa.Column("llm_cache_read_tokens", sa.Integer(), nullable=False),
        sa.Column("llm_output_tokens", sa.Integer(), nullable=False),
        # INTERVAL, o mesmo tipo de `turns.audio_duration` de onde o valor vem.
        # Um `stt_seconds` em `Float` ao lado de um INTERVAL criaria justamente a
        # divergência de unidade que o CARD-015 teria de resolver.
        sa.Column("stt_audio_duration", sa.Interval(), nullable=False),
        sa.Column("stt_provider", sa.String(length=40), nullable=False),
        # Volume, não custo: o Piper roda local (ADR-0032). Existe para que a
        # série histórica já exista no dia em que o TTS virar API paga.
        sa.Column("tts_chars", sa.Integer(), nullable=False),
        sa.Column("tts_provider", sa.String(length=40), nullable=False),
        # NUMERIC e **nunca** DOUBLE PRECISION: é a proibição de `float` para
        # dinheiro do ADR-0013 na forma que o banco entende. Escala 8 porque um
        # turn custa ~US$ 0,004 — com escala 2, toda linha deste produto gravaria
        # zero.
        #
        # **Nulável, e o nulo significa "não sabemos precificar este modelo"** —
        # diferente de `0`, que é o custo verdadeiro do STT e do TTS locais. É a
        # mesma distinção que o card faz sobre `cache_read = 0`, do outro lado.
        sa.Column(
            "estimated_cost_usd", sa.Numeric(precision=12, scale=8), nullable=True
        ),
        sa.ForeignKeyConstraint(["turn_id"], ["turns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("turn_id"),
    )
    # **A ordem das colunas é a decisão, não o alfabeto:** `student_id` primeiro
    # porque é igualdade, `occurred_at` depois porque é intervalo — um índice
    # composto só serve à faixa depois de ter fixado a igualdade. Invertido, ele
    # viraria uma varredura do período inteiro, de todos os alunos.
    #
    # É o único índice deste card no caminho crítico de um request: sem ele, a
    # decisão de cota do CARD-015 fica lenta **em silêncio**, proporcional ao
    # total de turns já processados no produto inteiro — o tipo de coisa que não
    # aparece com 10 linhas em desenvolvimento.
    op.create_index(
        "ix_usage_events_student_occurred",
        "usage_events",
        ["student_id", "occurred_at"],
    )


def downgrade() -> None:
    """Desfaz a tabela. O índice cai junto, e nenhum tipo fica órfão.

    O contraste com o ``downgrade`` do CARD-013 é o ponto: lá, ``drop_table``
    deixava dois tipos enum órfãos que faziam a próxima subida falhar, e removê-los
    à mão era obrigatório. Aqui não há tipo nenhum a remover — a decisão de usar
    ``VARCHAR`` para modelo e provider cobrou o preço uma vez (nenhuma validação
    do banco sobre o conjunto de valores) e devolveu isto.
    """
    op.drop_table("usage_events")
