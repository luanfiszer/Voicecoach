"""Modelos SQLAlchemy — a forma das linhas no Postgres (ADR-0004).

Estes **não** são as entidades de domínio. A separação é deliberada: o modelo
aqui responde ao banco (tipos, chaves, índices), a entidade responde ao negócio.
Usar o modelo mapeado como entidade é o atalho que a skill de arquitetura
proíbe — ele arrasta SQLAlchemy para dentro do núcleo pela porta dos fundos.

Sufixo ``Row`` em vez de ``Model``/``Entity`` para que a leitura de um import
misto (``Turn`` e ``TurnRow`` no mesmo arquivo de mapeamento) diga na hora quem
é quem.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Interval,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from voicecoach.domain.correction import CorrectionType, Severity
from voicecoach.domain.turn import TurnStatus


class Base(DeclarativeBase):
    """Base declarativa — o registro de metadados que o Alembic lê.

    Equivalente mental: o ``DbContext`` só na parte de "modelo"; a parte de
    "unidade de trabalho" é a ``AsyncSession``, que vive em ``engine.py``.
    """


# `DateTime(timezone=True)` vira TIMESTAMPTZ no Postgres. Não é preciosismo: a
# quota reseta por **dia-calendário em fuso fixo** ("renova às 00:00, horário de
# Brasília"), e essa conta é impossível de fazer certo sobre timestamp ingênuo.
_Timestamp = DateTime(timezone=True)

# `values_callable` faz o Postgres guardar o *valor* do membro ("queued") e não
# o *nome* ("QUEUED"). Sem isso, o que está no banco não é o que trafega no
# JSON, e a diferença só aparece quando alguém lê o banco na mão.
_TurnStatusType = Enum(
    TurnStatus,
    name="turn_status",
    values_callable=lambda enum: [member.value for member in enum],
)

# Os dois enums da correção seguem exatamente a mesma regra, e ela morde mais
# aqui: `values_callable` é o que faz o Postgres guardar "word_order" e não
# "WORD_ORDER". Sem ele, o valor no banco divergiria do valor no JSON — e a
# política aditiva do ADR-0008 (acrescentar membro pode, renomear não) passaria
# a ter DOIS nomes para proteger em vez de um.
_CorrectionTypeType = Enum(
    CorrectionType,
    name="correction_type",
    values_callable=lambda enum: [member.value for member in enum],
)

_SeverityType = Enum(
    Severity,
    name="correction_severity",
    values_callable=lambda enum: [member.value for member in enum],
)


class StudentRow(Base):
    __tablename__ = "students"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(_Timestamp)


class SessionRow(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    student_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("students.id"), index=True
    )
    started_at: Mapped[datetime] = mapped_column(_Timestamp)
    # Nulo significa "em andamento" — o estado da Session é derivado, não
    # gravado (mesmo princípio do ADR-0016).
    ended_at: Mapped[datetime | None] = mapped_column(_Timestamp, default=None)


class TurnRow(Base):
    """Turno da conversa.

    A quantidade de colunas nulas é intencional: nulo aqui significa "esta etapa
    ainda não aconteceu", e é exatamente isso que permite **derivar** a etapa
    exibida ao app em vez de gravá-la num campo que pode divergir do payload
    (ADR-0023).

    Note o que **não** está aqui: nenhuma coluna `stage` e nenhuma
    `delivered_partially`. As duas são propriedades calculadas da entidade — é a
    regra do ADR-0023 (herdada do 0016) de não persistir o que se consegue
    derivar. A tentação de gravar `stage` "para facilitar a query operacional" é
    nomeada como risco no CARD-018 justamente porque parece razoável.
    """

    __tablename__ = "turns"
    __table_args__ = (
        Index(
            "ix_turns_idempotency_key",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sessions.id"), index=True
    )
    input_audio_ref: Mapped[str] = mapped_column(String(512))
    # INTERVAL do Postgres ↔ `timedelta` do Python, sem unidade implícita no
    # nome da coluna. `SUM(audio_duration)` responde "quantos minutos falei
    # hoje?" direto no banco (CARD-015).
    audio_duration: Mapped[timedelta] = mapped_column(Interval)
    created_at: Mapped[datetime] = mapped_column(_Timestamp)

    # Idempotência do POST (CARD-010). O índice é ÚNICO e **parcial**: só vale
    # onde a chave existe, porque o worker e os testes criam Turn sem passar
    # pela borda HTTP, e vários nulos não podem colidir entre si.
    #
    # Por que aqui e não no Redis: um `SETNX` com TTL cria uma segunda fonte de
    # verdade e um estado de crash sem saída — a chave existindo e apontando
    # para nenhum Turn. Aqui a chave e o Turn nascem no MESMO commit, então os
    # dois existem ou nenhum existe. O preço é uma migration e uma decisão de
    # retenção: a chave é dado do cliente e morre junto do Turn, sem ciclo
    # próprio.
    idempotency_key: Mapped[str | None] = mapped_column(String(255), default=None)

    status: Mapped[TurnStatus] = mapped_column(_TurnStatusType, index=True)

    transcript: Mapped[str | None] = mapped_column(Text, default=None)
    transcribed_at: Mapped[datetime | None] = mapped_column(_Timestamp, default=None)

    reply_text: Mapped[str | None] = mapped_column(Text, default=None)
    replied_at: Mapped[datetime | None] = mapped_column(_Timestamp, default=None)

    # Nulo COM `synthesized_at` preenchido = o áudio existiu e expirou
    # (CARD-017); ambos nulos = nunca houve áudio. A distinção que a tela de
    # histórico faz ("áudio expirado — transcrição permanece") não precisa de
    # coluna extra.
    reply_audio_ref: Mapped[str | None] = mapped_column(String(512), default=None)
    synthesized_at: Mapped[datetime | None] = mapped_column(_Timestamp, default=None)

    failure_reason: Mapped[str | None] = mapped_column(Text, default=None)
    failed_at: Mapped[datetime | None] = mapped_column(_Timestamp, default=None)

    started_processing_at: Mapped[datetime | None] = mapped_column(
        _Timestamp, default=None
    )
    completed_at: Mapped[datetime | None] = mapped_column(_Timestamp, default=None)

    # `order_by` fixa a ordem de playback na própria definição do relacionamento:
    # quem carregar a coleção recebe os trechos ordenados sem lembrar de pedir.
    # Ordenar por `index` e não por `created_at` é decisão do ADR-0023 — dois
    # trechos podem ficar prontos no mesmo milissegundo.
    #
    # `cascade="all, delete-orphan"` diz que o trecho não vive sem o turn: é
    # entidade filha do agregado, e o delete de conta do CARD-017 não deve
    # precisar saber que esta tabela existe.
    audio_chunks: Mapped[list[TurnAudioChunkRow]] = relationship(
        order_by="TurnAudioChunkRow.index",
        lazy="raise_on_sql",
        cascade="all, delete-orphan",
    )

    # A segunda coleção filha (CARD-013), declarada com exatamente as mesmas três
    # opções — e a repetição é deliberada, não copy-paste esquecido:
    #
    # - `order_by` fixa a ordem PEDAGÓGICA na definição, do mesmo jeito que a de
    #   playback: quem carrega recebe ordenado sem lembrar de pedir, e é dessa
    #   ordem que `legacy_summary` tira a correção que representa o turn;
    # - `lazy="raise_on_sql"` transforma o "esqueci o eager load" de N+1
    #   silencioso em erro na hora (ver o docstring do repositório);
    # - `cascade="all, delete-orphan"` diz que a correção não vive sem o turn, o
    #   que mantém o delete de conta do CARD-017 ignorante desta tabela.
    corrections: Mapped[list[CorrectionRow]] = relationship(
        order_by="CorrectionRow.index",
        lazy="raise_on_sql",
        cascade="all, delete-orphan",
    )


class TurnAudioChunkRow(Base):
    """Um trecho de áudio da resposta (ADR-0023).

    **Chave primária composta `(turn_id, index)`**, e não um id surrogate: o par
    já é a identidade natural do trecho, e a PK composta entrega de graça a
    unicidade que a invariante de índice denso exige do lado do banco. Um id
    próprio seria uma coluna a mais sem pergunta que ela responda — e a entidade
    de domínio não tem id de trecho para mapear nele.

    Por que a mesma regra existe nos dois lados: a do domínio protege de lógica
    errada (o worker se enganou na conta), a do banco protege de duas escritas
    concorrentes que passaram pela do domínio cada uma no seu processo.
    """

    __tablename__ = "turn_audio_chunks"

    turn_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("turns.id", ondelete="CASCADE"), primary_key=True
    )
    # `index` é palavra não-reservada no Postgres, logo vale como nome de coluna.
    # Mantido igual ao nome do domínio (ADR-0023) para não abrir tradução entre
    # entidade e linha onde não há necessidade.
    index: Mapped[int] = mapped_column(Integer, primary_key=True)
    storage_key: Mapped[str] = mapped_column(String(512))
    # `Float` (double precision) e não Decimal: duração de playback não é
    # dinheiro — a proibição de float do ADR-0013 é sobre valor monetário, e
    # aqui erro de arredondamento em microssegundos não tem consequência.
    duration_seconds: Mapped[float] = mapped_column(Float)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(_Timestamp)


class CorrectionRow(Base):
    """Uma correção da fala do aluno (CARD-013) — a entidade mais valiosa do produto.

    **Chave primária composta ``(turn_id, index)``**, pelo mesmo motivo do
    trecho de áudio: o par já é a identidade natural, e a PK composta entrega de
    graça a unicidade que a invariante de índice denso exige do lado do banco.

    O que **não** está aqui: nenhuma coluna de timestamp. Todas as correções de
    um turn nascem no instante do ``replied_at`` dele, e uma coluna por linha
    para repetir esse valor N vezes é o dado duplicado que o ADR-0016 recusa.
    Nenhuma coluna ``has_mistakes``/``original``/``corrected``/``tip`` também: os
    quatro campos do contrato ``/v1`` são **derivados** desta tabela por
    ``legacy_summary``, e persisti-los seria a mesma verdade gravada duas vezes.

    ``Text`` e não ``String(n)`` nos três campos livres: nenhum deles tem limite
    que o negócio saiba defender, e um ``VARCHAR`` apertado transformaria uma
    explicação longa do professor em erro de escrita no fim do pipeline. No
    Postgres os dois têm o mesmo desempenho.
    """

    __tablename__ = "turn_corrections"

    turn_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("turns.id", ondelete="CASCADE"), primary_key=True
    )
    index: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[CorrectionType] = mapped_column(_CorrectionTypeType)
    original_excerpt: Mapped[str] = mapped_column(Text)
    corrected_form: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text)
    severity: Mapped[Severity] = mapped_column(_SeverityType)
