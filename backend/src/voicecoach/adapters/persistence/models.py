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

from sqlalchemy import DateTime, Enum, ForeignKey, Interval, String, Text, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

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
    (ADR-0016).
    """

    __tablename__ = "turns"

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
