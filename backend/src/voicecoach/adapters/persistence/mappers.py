"""Tradução entidade ↔ linha.

Cerimônia consciente (o CARD-005 a registra como risco): é o preço de o domínio
não conhecer SQLAlchemy. O atalho seria usar ``TurnRow`` como entidade — e aí
toda regra de negócio passaria a carregar um objeto atado a uma sessão de banco.

As funções são livres, não métodos: mapear não é comportamento nem da entidade
(que não conhece persistência) nem da linha.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from voicecoach.adapters.persistence.models import (
    CorrectionRow,
    SessionRow,
    StudentRow,
    TurnAudioChunkRow,
    TurnRow,
    UsageEventRow,
)
from voicecoach.domain.correction import Correction
from voicecoach.domain.session import Session
from voicecoach.domain.student import Student
from voicecoach.domain.turn import Turn, TurnAudioChunk
from voicecoach.domain.usage import UsageEvent

if TYPE_CHECKING:
    from uuid import UUID


class StaleTurnError(RuntimeError):
    """A linha no banco tem mais trechos do que a entidade que se quer gravar.

    Não é erro de domínio (ADR-0017): nenhuma invariante de negócio foi
    violada — o chamador está gravando por cima de um Turn que outra escrita
    já avançou. É bug de orquestração, e pertence a esta camada.

    Existe porque a alternativa era pior: como ``apply_turn`` só **acrescenta**
    trechos, uma entidade defasada simplesmente não escreveria nada e a
    divergência ficaria invisível. Gatilho para trocar por locking otimista de
    verdade: o pipeline do CARD-009 passar a ter mais de um escritor por turn.
    """


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
        idempotency_key=turn.idempotency_key,
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
        audio_chunks=[chunk_to_row(turn.id, chunk) for chunk in turn.audio_chunks],
        corrections=[
            correction_to_row(turn.id, correction) for correction in turn.corrections
        ],
    )


def turn_from_row(row: TurnRow) -> Turn:
    return Turn(
        id=row.id,
        session_id=row.session_id,
        input_audio_ref=row.input_audio_ref,
        audio_duration=row.audio_duration,
        created_at=row.created_at,
        idempotency_key=row.idempotency_key,
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
        # O `order_by` do relationship já entrega ordenado por `index`; a
        # entidade herda a ordem de playback sem reordenar aqui.
        audio_chunks=[chunk_from_row(chunk) for chunk in row.audio_chunks],
        # Mesma coisa aqui: o `order_by` do relationship entrega a coleção na
        # ordem pedagógica, que é a ordem que `legacy_summary` lê.
        corrections=[correction_from_row(c) for c in row.corrections],
    )


def apply_turn(turn: Turn, row: TurnRow) -> None:
    """Copia para a linha carregada tudo que o pipeline pode ter produzido.

    ``id``, ``session_id``, ``input_audio_ref``, ``audio_duration``,
    ``created_at`` e ``idempotency_key`` ficam de fora de propósito: são
    imutáveis depois que o Turn nasce, e reescrevê-los aqui esconderia um bug em
    vez de deixá-lo estourar.
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
    _append_new_chunks(turn, row)
    _append_new_corrections(turn, row)


def _append_new_chunks(turn: Turn, row: TurnRow) -> None:
    """Acrescenta à linha só os trechos que ela ainda não tem.

    **Acrescentar, e não reatribuir a lista.** Trocar `row.audio_chunks` por uma
    lista nova faria o `delete-orphan` marcar os trechos antigos para remoção e
    o SQLAlchemy reinseri-los — que é o oposto da invariante do ADR-0023
    ("trecho entregue não é apagado") e ainda esbarraria na chave primária
    composta. Trecho é append-only e imutável; o mapeamento tem de dizer isso.
    """
    ja_gravados = len(row.audio_chunks)
    if ja_gravados > len(turn.audio_chunks):
        raise StaleTurnError(
            f"Turn {turn.id}: a linha tem {ja_gravados} trechos e a entidade "
            f"{len(turn.audio_chunks)} — gravação sobre estado defasado."
        )
    for chunk in turn.audio_chunks[ja_gravados:]:
        row.audio_chunks.append(chunk_to_row(turn.id, chunk))


def _append_new_corrections(turn: Turn, row: TurnRow) -> None:
    """Acrescenta à linha as correções que ela ainda não tem.

    Mesma forma de ``_append_new_chunks``, e pela mesma razão — reatribuir a
    lista faria o ``delete-orphan`` apagar e reinserir —, mas com uma invariante
    mais forte do lado de cá: ``Turn.attach_corrections`` é **write-once**, então
    "a linha já tem correções" só pode significar duas coisas, e nenhuma é
    normal. Ou é uma reexecução do pipeline sobre um turn já respondido (que o
    handler recusa antes de chegar aqui), ou são dois escritores no mesmo turn.

    Por isso a divergência é ``StaleTurnError``, e não um append silencioso: uma
    correção duplicada não estoura chave primária — ela ocuparia o índice
    seguinte e apareceria na tela do aluno como um erro que ele não cometeu.
    """
    ja_gravadas = len(row.corrections)
    if ja_gravadas and ja_gravadas != len(turn.corrections):
        raise StaleTurnError(
            f"Turn {turn.id}: a linha tem {ja_gravadas} correções e a entidade "
            f"{len(turn.corrections)} — gravação sobre estado defasado."
        )
    for correction in turn.corrections[ja_gravadas:]:
        row.corrections.append(correction_to_row(turn.id, correction))


def correction_to_row(turn_id: UUID, correction: Correction) -> CorrectionRow:
    return CorrectionRow(
        turn_id=turn_id,
        index=correction.index,
        type=correction.type,
        original_excerpt=correction.original_excerpt,
        corrected_form=correction.corrected_form,
        explanation=correction.explanation,
        severity=correction.severity,
    )


def correction_from_row(row: CorrectionRow) -> Correction:
    return Correction(
        index=row.index,
        type=row.type,
        original_excerpt=row.original_excerpt,
        corrected_form=row.corrected_form,
        explanation=row.explanation,
        severity=row.severity,
    )


def chunk_to_row(turn_id: UUID, chunk: TurnAudioChunk) -> TurnAudioChunkRow:
    return TurnAudioChunkRow(
        turn_id=turn_id,
        index=chunk.index,
        storage_key=chunk.storage_key,
        duration_seconds=chunk.duration_seconds,
        text=chunk.text,
        created_at=chunk.created_at,
    )


def chunk_from_row(row: TurnAudioChunkRow) -> TurnAudioChunk:
    return TurnAudioChunk(
        index=row.index,
        storage_key=row.storage_key,
        duration_seconds=row.duration_seconds,
        text=row.text,
        created_at=row.created_at,
    )


def usage_event_to_row(event: UsageEvent) -> UsageEventRow:
    """Uma linha de custo. **Não há ``apply_usage_event``**, e a falta é a regra.

    Medição não se corrige: o turn consumiu o que consumiu. Um ``apply_*`` aqui
    seria a porta pela qual um número que alguém já somou muda de valor sem
    deixar rastro — e o repositório, coerentemente, não tem ``update``.
    """
    return UsageEventRow(
        turn_id=event.turn_id,
        student_id=event.student_id,
        occurred_at=event.occurred_at,
        llm_model=event.llm_model,
        llm_input_tokens=event.llm_input_tokens,
        llm_cache_creation_tokens=event.llm_cache_creation_tokens,
        llm_cache_read_tokens=event.llm_cache_read_tokens,
        llm_output_tokens=event.llm_output_tokens,
        stt_audio_duration=event.stt_audio_duration,
        stt_provider=event.stt_provider,
        tts_chars=event.tts_chars,
        tts_provider=event.tts_provider,
        estimated_cost_usd=event.estimated_cost_usd,
    )


def usage_event_from_row(row: UsageEventRow) -> UsageEvent:
    return UsageEvent(
        turn_id=row.turn_id,
        student_id=row.student_id,
        occurred_at=row.occurred_at,
        llm_model=row.llm_model,
        llm_input_tokens=row.llm_input_tokens,
        llm_cache_creation_tokens=row.llm_cache_creation_tokens,
        llm_cache_read_tokens=row.llm_cache_read_tokens,
        llm_output_tokens=row.llm_output_tokens,
        stt_audio_duration=row.stt_audio_duration,
        stt_provider=row.stt_provider,
        tts_chars=row.tts_chars,
        tts_provider=row.tts_provider,
        estimated_cost_usd=row.estimated_cost_usd,
    )
