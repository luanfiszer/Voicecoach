"""Contrato HTTP da listagem de sessões (CARD-030, artboard 10)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from voicecoach.application.use_cases.list_sessions import SessionListItem


class SessionListEntry(BaseModel):
    """Uma sessão na listagem do histórico."""

    id: UUID
    started_at: datetime
    ended_at: datetime | None = Field(
        default=None, description="Nulo significa em andamento (ADR-0016)."
    )
    spoken_seconds: float = Field(
        description="Soma de audio_duration dos turns — a MESMA definição do "
        "resumo pós-sessão (CARD-031). Uma definição, um lugar."
    )
    turns: int
    corrections: int
    reply_media_available: bool = Field(
        description="`false` significa **não conte com o áudio** — é uma "
        "previsão conservadora sobre a retenção vigente (ADR-0024), não uma "
        "leitura do bucket. Nunca calcule isto no cliente pela data: a "
        "política é configuração e muda sem avisar o app."
    )

    @classmethod
    def de_item(cls, item: SessionListItem) -> SessionListEntry:
        return cls(
            id=item.digest.id,
            started_at=item.digest.started_at,
            ended_at=item.digest.ended_at,
            spoken_seconds=item.digest.spoken.total_seconds(),
            turns=item.digest.turns,
            corrections=item.digest.corrections,
            reply_media_available=item.reply_media_available,
        )


class SessionListResponse(BaseModel):
    """``GET /v1/sessions`` — envelope, e não uma lista nua.

    Uma lista JSON no topo da resposta é contrato que não cresce: acrescentar
    "quantas ficaram fora da janela" ou paginação depois exigiria mudar o tipo
    raiz, que é justamente o que o ADR-0008 proíbe dentro de `/v1`. O envelope
    custa uma linha hoje e mantém a evolução aditiva possível.
    """

    sessions: list[SessionListEntry]
    window_days: int = Field(
        description="A janela efetivamente aplicada — o cliente não precisa "
        "lembrar o default que pediu."
    )
