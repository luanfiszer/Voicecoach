"""Tradução entidade ↔ linha.

Cerimônia consciente (o CARD-005 a registra como risco): é o preço de o domínio
não conhecer SQLAlchemy. O atalho seria usar ``TurnRow`` como entidade — e aí
toda regra de negócio passaria a carregar um objeto atado a uma sessão de banco.

As funções são livres, não métodos: mapear não é comportamento nem da entidade
(que não conhece persistência) nem da linha.
"""

from __future__ import annotations

from voicecoach.adapters.persistence.models import SessionRow, StudentRow, TurnRow
from voicecoach.domain.session import Session
from voicecoach.domain.student import Student
from voicecoach.domain.turn import Turn


def student_to_row(student: Student) -> StudentRow:
    return StudentRow(
        id=student.id,
        display_name=student.display_name,
        created_at=student.created_at,
    )


def student_from_row(row: StudentRow) -> Student:
    return Student(
        id=row.id,
        display_name=row.display_name,
        created_at=row.created_at,
    )


def session_to_row(session: Session) -> SessionRow:
    return SessionRow(
        id=session.id,
        student_id=session.student_id,
        started_at=session.started_at,
        ended_at=session.ended_at,
    )


def session_from_row(row: SessionRow) -> Session:
    return Session(
        id=row.id,
        student_id=row.student_id,
        started_at=row.started_at,
        ended_at=row.ended_at,
    )


def apply_session(session: Session, row: SessionRow) -> None:
    """Copia para a linha carregada o que pode ter mudado."""
    row.ended_at = session.ended_at


def turn_to_row(turn: Turn) -> TurnRow:
    return TurnRow(
        id=turn.id,
        session_id=turn.session_id,
        input_audio_ref=turn.input_audio_ref,
        audio_duration=turn.audio_duration,
        created_at=turn.created_at,
        status=turn.status,
        transcript=turn.transcript,
        transcribed_at=turn.transcribed_at,
        reply_text=turn.reply_text,
        replied_at=turn.replied_at,
        reply_audio_ref=turn.reply_audio_ref,
        synthesized_at=turn.synthesized_at,
        failure_reason=turn.failure_reason,
        failed_at=turn.failed_at,
        started_processing_at=turn.started_processing_at,
        completed_at=turn.completed_at,
    )


def turn_from_row(row: TurnRow) -> Turn:
    return Turn(
        id=row.id,
        session_id=row.session_id,
        input_audio_ref=row.input_audio_ref,
        audio_duration=row.audio_duration,
        created_at=row.created_at,
        status=row.status,
        transcript=row.transcript,
        transcribed_at=row.transcribed_at,
        reply_text=row.reply_text,
        replied_at=row.replied_at,
        reply_audio_ref=row.reply_audio_ref,
        synthesized_at=row.synthesized_at,
        failure_reason=row.failure_reason,
        failed_at=row.failed_at,
        started_processing_at=row.started_processing_at,
        completed_at=row.completed_at,
    )


def apply_turn(turn: Turn, row: TurnRow) -> None:
    """Copia para a linha carregada tudo que o pipeline pode ter produzido.

    ``id``, ``session_id``, ``input_audio_ref``, ``audio_duration`` e
    ``created_at`` ficam de fora de propósito: são imutáveis depois que o Turn
    nasce, e reescrevê-los aqui esconderia um bug em vez de deixá-lo estourar.
    """
    row.status = turn.status
    row.transcript = turn.transcript
    row.transcribed_at = turn.transcribed_at
    row.reply_text = turn.reply_text
    row.replied_at = turn.replied_at
    row.reply_audio_ref = turn.reply_audio_ref
    row.synthesized_at = turn.synthesized_at
    row.failure_reason = turn.failure_reason
    row.failed_at = turn.failed_at
    row.started_processing_at = turn.started_processing_at
    row.completed_at = turn.completed_at
