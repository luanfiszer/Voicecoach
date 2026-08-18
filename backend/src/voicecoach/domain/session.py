"""``Session`` — uma conversa com início e fim explícitos (visão §A).

É a unidade de relatório do produto: o "Sessão de hoje · 4 turnos · 6 min" da
tela de conversa e o resumo pós-sessão contam sobre ela. No protótipo de
WhatsApp isso não existia (era uma thread infinita).

O estado é **derivado**, não gravado: ``ended_at`` nulo significa em andamento.
Mesmo princípio do ADR-0016 — não persistir o que se consegue derivar, porque
dado duplicado é dado que sai de sincronia.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from voicecoach.domain.errors import InvalidStateTransitionError
from voicecoach.domain.turn import Turn


@dataclass
class Session:
    """Uma conversa do aluno com o professor."""

    id: UUID
    student_id: UUID
    started_at: datetime
    ended_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        """Em andamento enquanto ninguém encerrou."""
        return self.ended_at is None

    def start_turn(
        self,
        *,
        turn_id: UUID,
        input_audio_ref: str,
        audio_duration: timedelta,
        now: datetime,
    ) -> Turn:
        """Cria um Turn nesta sessão — e recusa se ela já foi encerrada.

        Esta invariante parece teórica e não é: o app guarda a gravação no
        aparelho quando está sem conexão ("sua fala está guardada aqui, vai
        sozinho quando a conexão voltar"), então uma fala gravada às 21h pode
        chegar ao servidor às 23h, depois de a sessão ter sido encerrada. Sem a
        recusa, o Turn entraria numa sessão morta e sumiria da interface.

        A fábrica vive aqui, e não num construtor de ``Turn``, porque a regra é
        sobre a **sessão**: só quem conhece o próprio estado pode decidir se
        aceita mais um turno. E note que ela não carrega a lista de turns —
        validar o estado não exige a coleção inteira na memória.
        """
        if not self.is_active:
            raise InvalidStateTransitionError(
                entity="Session", action="start_turn", state="ended"
            )
        return Turn(
            id=turn_id,
            session_id=self.id,
            input_audio_ref=input_audio_ref,
            audio_duration=audio_duration,
            created_at=now,
        )

    def end(self, now: datetime) -> None:
        """Encerra a sessão — é ação explícita do aluno ("Encerrar")."""
        if not self.is_active:
            raise InvalidStateTransitionError(
                entity="Session", action="end", state="ended"
            )
        if now < self.started_at:
            message = "Session: não é possível encerrar antes do início."
            raise ValueError(message)
        self.ended_at = now
